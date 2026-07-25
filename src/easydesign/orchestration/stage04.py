"""Stage 04 resumable multi-GPU BoltzGen pilot orchestration."""

from __future__ import annotations

import hashlib
import json
import shutil
import threading
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from easydesign.backends.boltzgen import (
    BoltzGenGenerationAdapter,
    BoltzGenGenerationRequest,
)
from easydesign.backends.executors import GpuResourceSnapshot, NvidiaSmiProbe, execute_on_devices
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
from easydesign.core.timestamps import normalize_aware_datetime
from easydesign.stages.s03_boltzgen_configuration import StrategyBundle
from easydesign.stages.s04_pilot_generation import (
    CandidateIndex,
    CandidateRecord,
    PilotBundle,
    PilotExecutionState,
    PilotPlan,
    PilotStrategyPlan,
    TaskTable,
    collect_boltzgen_candidates,
)

from .task_tracking import TaskEventJournal, atomic_dump_runtime_model
from .workspace import ResolvedRunConfig, RunIndexEntry, upsert_run_index_entries


class Stage04Execution(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    status: str
    run_root: Path
    run_manifest: Path
    stage_manifest: Path | None = None
    pilot_bundle: Path | None = None
    strategy_count: int
    complete_candidate_count: int


@dataclass(frozen=True, slots=True)
class _Upstream:
    run: RunManifest
    run_manifest_path: Path
    stage03: StageManifest
    stage03_manifest_ref: ArtifactRef
    strategy_bundle_ref: ArtifactRef
    strategy_bundle: StrategyBundle


def _latest_manifest(root: Path) -> tuple[RunManifest, Path]:
    pointer = root / "manifests" / "LATEST"
    try:
        name = pointer.read_text(encoding="utf-8").strip()
    except OSError as error:
        raise ManifestStateError(f"无法读取 RunManifest LATEST: {pointer}") from error
    path = root / "manifests" / name
    return load_model(path, RunManifest), path


def _atomic_text(value: str, path: Path) -> None:
    from .stage03 import _atomic_text as stage03_atomic_text

    stage03_atomic_text(value, path)


def _artifact(
    root: Path,
    path: Path,
    *,
    artifact_id: str,
    role: str,
    file_format: str,
    attempt_id: str = "attempt-0001",
) -> ArtifactRef:
    return ArtifactRef.from_file(
        run_root=root,
        relative_path=path.relative_to(root).as_posix(),
        artifact_id=artifact_id,
        role=role,
        file_format=file_format,
        producer_stage=str(StageId.PILOT_GENERATION),
        producer_attempt=attempt_id,
    )


def _load_upstream(root: Path) -> _Upstream:
    run, run_path = _latest_manifest(root)
    stage03_ref = next(
        (
            reference
            for reference in run.stage_manifest_refs
            if reference.producer_stage == str(StageId.BOLTZGEN_CONFIGURATION)
        ),
        None,
    )
    if stage03_ref is None:
        raise ManifestStateError("Stage 04 必须获得当前 Stage 03 manifest")
    stage03 = load_model(stage03_ref.verify(root), StageManifest)
    if stage03.status is not ExecutionStatus.SUCCEEDED:
        raise ManifestStateError("Stage 03 未成功，不能执行 Stage 04")
    strategy_bundle_ref = stage03.require_output("strategy-bundle")
    strategy_bundle_path = strategy_bundle_ref.verify(root)
    strategy_bundle = load_model(strategy_bundle_path, StrategyBundle)
    for strategy in strategy_bundle.strategies:
        specification = stage03.require_output(f"strategy-{strategy.strategy_id}")
        if specification.sha256 != strategy.design_specification_sha256:
            raise ManifestStateError(
                f"StrategyBundle 与 StageManifest YAML identity 不一致: {strategy.strategy_id}"
            )
        specification.verify(root)
    return _Upstream(
        run=run,
        run_manifest_path=run_path,
        stage03=stage03,
        stage03_manifest_ref=stage03_ref,
        strategy_bundle_ref=strategy_bundle_ref,
        strategy_bundle=strategy_bundle,
    )


def _build_plan(
    *,
    root: Path,
    upstream: _Upstream,
    resolved: ResolvedRunConfig,
    generated_at: datetime,
) -> PilotPlan:
    config = resolved.user_config.stage04
    if config is None:
        raise ManifestStateError("run config 没有 Stage 04 配置")
    strategies: list[PilotStrategyPlan] = []
    for strategy in upstream.strategy_bundle.strategies:
        specification = upstream.stage03.require_output(f"strategy-{strategy.strategy_id}")
        strategies.append(
            PilotStrategyPlan(
                task_id=f"pilot-{strategy.strategy_id}",
                strategy_id=strategy.strategy_id,
                design_specification=specification,
                required_complete_candidates=(config.required_complete_candidates_per_strategy),
            )
        )
    return PilotPlan(
        generated_at=generated_at,
        strategy_bundle_sha256=upstream.strategy_bundle_ref.sha256,
        devices=config.executor.devices,
        strategies=tuple(strategies),
    )


def _command_sha256(command: tuple[str, ...]) -> str:
    return hashlib.sha256(json.dumps(command, separators=(",", ":")).encode("utf-8")).hexdigest()


def _snapshot(
    *,
    tasks: tuple[TaskRecord, ...],
    updated_at: datetime,
    started_monotonic: float,
    planned_candidates: int,
    status: str,
    recent_errors: tuple[str, ...] = (),
) -> ProgressSnapshot:
    counts = {item: 0 for item in TaskStatus}
    per_device: dict[str, str | None] = {}
    for task in tasks:
        counts[task.status] += 1
        if task.status is TaskStatus.RUNNING:
            assert task.current_device is not None
            per_device[str(task.current_device)] = task.strategy_id
    collected = sum(task.collected_candidates for task in tasks)
    elapsed = max(time.monotonic() - started_monotonic, 0)
    throughput = collected / elapsed * 3600 if collected > 0 and elapsed > 0 else None
    remaining = planned_candidates - collected
    eta = (
        remaining / throughput * 3600
        if throughput is not None and throughput > 0 and remaining > 0
        else (0.0 if remaining == 0 else None)
    )
    return ProgressSnapshot(
        stage_id=str(StageId.PILOT_GENERATION),
        updated_at=updated_at,
        status=status,
        total_tasks=len(tasks),
        pending_tasks=counts[TaskStatus.PENDING],
        waiting_tasks=counts[TaskStatus.WAITING_RESOURCE],
        running_tasks=counts[TaskStatus.RUNNING],
        succeeded_tasks=counts[TaskStatus.SUCCEEDED],
        failed_tasks=counts[TaskStatus.FAILED],
        planned_candidates=planned_candidates,
        collected_candidates=collected,
        per_device=per_device,
        elapsed_seconds=elapsed,
        throughput_candidates_per_hour=throughput,
        estimated_remaining_seconds=eta,
        recent_errors=recent_errors[-10:],
    )


def _json_payload(path: Path, payload: object) -> None:
    if path.exists():
        raise ManifestStateError(f"禁止覆盖 Stage 04 artifact: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            payload,
            ensure_ascii=False,
            allow_nan=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


def _rehydrate_design_mask_evidence(
    *,
    root: Path,
    attempt_id: str,
    tasks: dict[str, TaskRecord],
    candidates: list[CandidateRecord],
) -> int:
    """Upgrade resumable runtime records using declared task-attempt outputs."""

    missing = [
        candidate
        for candidate in candidates
        if candidate.design_mask_source is None
        or not candidate.designed_binder_residue_ids
    ]
    if not missing:
        return 0
    rebuilt: list[CandidateRecord] = []
    for task in tasks.values():
        ordinal = 1
        task_candidates: list[CandidateRecord] = []
        for task_attempt in task.attempts:
            if (
                task_attempt.status is TaskStatus.RUNNING
                or task_attempt.collected_candidates == 0
            ):
                continue
            output = root / task_attempt.output_relative_path
            collected = collect_boltzgen_candidates(
                run_root=root,
                backend_output=output,
                strategy_id=task.strategy_id,
                task_id=task.task_id,
                task_attempt_number=task_attempt.attempt_number,
                stage_attempt_id=attempt_id,
                ordinal_start=ordinal,
                maximum_candidates=task_attempt.collected_candidates,
            )
            if len(collected) != task_attempt.collected_candidates:
                raise ManifestStateError(
                    f"task={task.task_id} attempt={task_attempt.attempt_number} "
                    "无法从已声明 backend output 恢复全部 design-mask evidence"
                )
            task_candidates.extend(collected)
            ordinal += len(collected)
        expected_ids = task.candidate_ids
        observed_ids = tuple(item.candidate_id for item in task_candidates)
        if observed_ids != expected_ids:
            raise ManifestStateError(
                f"task={task.task_id} design-mask evidence 重建改变了 candidate identity"
            )
        rebuilt.extend(task_candidates)
    if len(rebuilt) != len(candidates):
        raise ManifestStateError("design-mask evidence 重建候选总数不一致")
    candidates[:] = rebuilt
    return len(rebuilt)


def execute_stage04(
    *,
    run_root: Path,
    adapter: BoltzGenGenerationAdapter,
    gpu_probe: NvidiaSmiProbe | None = None,
    executed_at: datetime | None = None,
) -> Stage04Execution:
    """Execute or resume Stage 04; incomplete tasks remain explicitly resumable."""

    root = run_root.resolve()
    upstream = _load_upstream(root)
    if upstream.run.status is not ExecutionStatus.RUNNING:
        raise ManifestStateError("Stage 04 只能写入 running run")
    if any(
        reference.producer_stage == str(StageId.PILOT_GENERATION)
        for reference in upstream.run.stage_manifest_refs
    ):
        raise ManifestStateError("Stage 04 已发布，禁止覆盖")
    resolved = load_model(
        root / "config-snapshot" / "resolved-config.json",
        ResolvedRunConfig,
    )
    config = resolved.user_config.stage04
    if config is None:
        raise ManifestStateError("run config 没有 Stage 04 配置")
    now = datetime.now(UTC) if executed_at is None else normalize_aware_datetime(executed_at)
    attempt_id = "attempt-0001"
    attempt_root = root / str(StageId.PILOT_GENERATION) / attempt_id
    runtime_root = attempt_root / "runtime"
    artifacts = attempt_root / "artifacts"
    plan_path = artifacts / "pilot-plan.json"
    state_path = runtime_root / "task-state.json"
    progress_path = runtime_root / "progress.json"
    events_path = runtime_root / "task-events.jsonl"
    journal = TaskEventJournal(events_path)
    started_monotonic = time.monotonic()

    if plan_path.is_file():
        plan = load_model(plan_path, PilotPlan)
        if plan.strategy_bundle_sha256 != upstream.strategy_bundle_ref.sha256:
            raise ManifestStateError("Stage 04 现有 plan 与当前 StrategyBundle 不一致")
    else:
        plan = _build_plan(
            root=root,
            upstream=upstream,
            resolved=resolved,
            generated_at=now,
        )
        dump_model(plan, plan_path)
    plan_sha = sha256_file(plan_path)
    planned_candidates = sum(item.required_complete_candidates for item in plan.strategies)

    if state_path.is_file():
        state = load_model(state_path, PilotExecutionState)
        if state.plan_sha256 != plan_sha:
            raise ManifestStateError("Stage 04 runtime state 与 plan checksum 不一致")
        tasks = {task.task_id: task for task in state.tasks}
        candidates = list(state.candidates)
        created_at = state.created_at
    else:
        created_at = now
        tasks = {
            item.task_id: TaskRecord(
                task_id=item.task_id,
                strategy_id=item.strategy_id,
                requested_candidates=item.required_complete_candidates,
            )
            for item in plan.strategies
        }
        candidates = []

    rehydrated_candidate_count = _rehydrate_design_mask_evidence(
        root=root,
        attempt_id=attempt_id,
        tasks=tasks,
        candidates=candidates,
    )
    lock = threading.RLock()
    recent_errors: list[str] = []

    def ordered_tasks() -> tuple[TaskRecord, ...]:
        return tuple(tasks[item.task_id] for item in plan.strategies)

    def persist(status: str) -> None:
        snapshot = _snapshot(
            tasks=ordered_tasks(),
            updated_at=datetime.now(UTC),
            started_monotonic=started_monotonic,
            planned_candidates=planned_candidates,
            status=status,
            recent_errors=tuple(recent_errors),
        )
        atomic_dump_runtime_model(snapshot, progress_path)
        atomic_dump_runtime_model(
            PilotExecutionState(
                created_at=created_at,
                updated_at=snapshot.updated_at,
                plan_sha256=plan_sha,
                tasks=ordered_tasks(),
                candidates=tuple(candidates),
                progress=snapshot,
            ),
            state_path,
        )

    def append_event(
        *,
        event_type: str,
        message: str,
        task: TaskRecord | None = None,
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
                task_id=None if task is None else task.task_id,
                strategy_id=None if task is None else task.strategy_id,
                task_attempt_number=attempt_number,
                device=device,
                from_status=from_status,
                to_status=to_status,
                message=message,
                error=error,
            )
        )

    if rehydrated_candidate_count:
        append_event(
            event_type="candidate-evidence-upgraded",
            message=(
                f"Revalidated {rehydrated_candidate_count} existing candidates "
                "against BoltzGen official design_mask artifacts."
            ),
        )

    # A crashed process may leave a task marked running. Salvage any complete
    # candidate artifacts, then close that task attempt as interrupted.
    for task_id, task in tuple(tasks.items()):
        if task.status is not TaskStatus.RUNNING:
            continue
        running_attempt = task.attempts[-1]
        output = root / running_attempt.output_relative_path
        remaining = task.requested_candidates - task.collected_candidates
        salvaged = (
            collect_boltzgen_candidates(
                run_root=root,
                backend_output=output,
                strategy_id=task.strategy_id,
                task_id=task.task_id,
                task_attempt_number=running_attempt.attempt_number,
                stage_attempt_id=attempt_id,
                ordinal_start=task.collected_candidates + 1,
                maximum_candidates=max(remaining, 0),
            )
            if remaining > 0
            else ()
        )
        candidates.extend(salvaged)
        error = ErrorInfo(
            code="interrupted-before-resume",
            message="Previous EasyDesign process ended before task terminal state.",
            retryable=True,
        )
        closed_attempt = running_attempt.model_copy(
            update={
                "status": TaskStatus.FAILED,
                "collected_candidates": len(salvaged),
                "ended_at": datetime.now(UTC),
                "return_code": 130,
                "error": error,
            }
        )
        candidate_ids = (*task.candidate_ids, *(item.candidate_id for item in salvaged))
        tasks[task_id] = task.model_copy(
            update={
                "status": TaskStatus.PENDING,
                "collected_candidates": len(candidate_ids),
                "candidate_ids": candidate_ids,
                "attempts": (*task.attempts[:-1], closed_attempt),
                "current_device": None,
            }
        )
        append_event(
            event_type="task-interrupted",
            message="Recovered an interrupted task for resume.",
            task=tasks[task_id],
            attempt_number=running_attempt.attempt_number,
            device=running_attempt.device,
            from_status=TaskStatus.RUNNING,
            to_status=TaskStatus.PENDING,
            error=error,
        )
    with lock:
        for task_id, task in tuple(tasks.items()):
            if task.status is TaskStatus.PENDING:
                tasks[task_id] = task.model_copy(
                    update={"status": TaskStatus.WAITING_RESOURCE}
                )
        persist("waiting-resource")

    probe = NvidiaSmiProbe() if gpu_probe is None else gpu_probe

    def on_wait(busy: tuple[GpuResourceSnapshot, ...]) -> None:
        with lock:
            append_event(
                event_type="resource-wait",
                message="; ".join(
                    f"gpu={item.device},memory={item.memory_used_mib}MiB,"
                    f"util={item.utilization_percent}%,pids={item.compute_process_pids}"
                    for item in busy
                ),
            )
            persist("waiting-resource")

    gpu_snapshots = probe.wait_until_idle(
        config.executor.devices,
        max_memory_used_mib=config.executor.max_memory_used_mib,
        max_utilization_percent=config.executor.max_utilization_percent,
        timeout_seconds=config.executor.resource_wait_timeout_seconds,
        poll_seconds=config.executor.resource_poll_seconds,
        on_wait=on_wait,
    )
    with lock:
        for task_id, task in tuple(tasks.items()):
            if task.status is TaskStatus.WAITING_RESOURCE:
                tasks[task_id] = task.model_copy(update={"status": TaskStatus.PENDING})
    capability = adapter.probe()
    backend_environment_path = artifacts / "backend-environment.json"
    if not backend_environment_path.exists():
        _json_payload(
            backend_environment_path,
            {
                "schema_version": "0.1",
                "capability": capability,
                "gpu_preflight": [snapshot.model_dump(mode="json") for snapshot in gpu_snapshots],
                "executor": config.executor.model_dump(mode="json"),
            },
        )
    append_event(
        event_type="resources-ready",
        message=f"GPU devices ready: {config.executor.devices}",
    )
    persist("running")

    def execute_task(plan_item: PilotStrategyPlan, device: int) -> TaskRecord:
        with lock:
            task = tasks[plan_item.task_id]
        attempts_this_invocation = 0
        while (
            task.collected_candidates < task.requested_candidates
            and attempts_this_invocation < config.executor.max_task_attempts
        ):
            attempts_this_invocation += 1
            attempt_number = len(task.attempts) + 1
            remaining = task.requested_candidates - task.collected_candidates
            task_attempt_root = (
                attempt_root / "tasks" / task.task_id / f"attempt-{attempt_number:04d}"
            )
            output = task_attempt_root / "backend-output"
            stdout = task_attempt_root / "stdout.log"
            stderr = task_attempt_root / "stderr.log"
            request = BoltzGenGenerationRequest(
                design_specification=plan_item.design_specification.verify(root),
                output_directory=output,
                requested_candidates=remaining,
                physical_device=device,
                stdout_path=stdout,
                stderr_path=stderr,
            )
            command = adapter.build_command(request)
            started = datetime.now(UTC)
            running_attempt = TaskAttemptRecord(
                attempt_number=attempt_number,
                status=TaskStatus.RUNNING,
                requested_candidates=remaining,
                device=device,
                command_sha256=_command_sha256(command),
                output_relative_path=output.relative_to(root).as_posix(),
                started_at=started,
            )
            with lock:
                task = task.model_copy(
                    update={
                        "status": TaskStatus.RUNNING,
                        "attempts": (*task.attempts, running_attempt),
                        "current_device": device,
                    }
                )
                tasks[task.task_id] = task
                append_event(
                    event_type="task-started",
                    message=f"Requested {remaining} complete candidates.",
                    task=task,
                    attempt_number=attempt_number,
                    device=device,
                    from_status=TaskStatus.PENDING,
                    to_status=TaskStatus.RUNNING,
                )
                persist("running")
            operational_error: ErrorInfo | None = None
            return_code = 1
            ended = datetime.now(UTC)
            new_candidates: tuple[CandidateRecord, ...] = ()
            try:
                result = adapter.execute(request)
                return_code = result.return_code
                ended = result.ended_at
                new_candidates = collect_boltzgen_candidates(
                    run_root=root,
                    backend_output=result.output_directory,
                    strategy_id=task.strategy_id,
                    task_id=task.task_id,
                    task_attempt_number=attempt_number,
                    stage_attempt_id=attempt_id,
                    ordinal_start=task.collected_candidates + 1,
                    maximum_candidates=remaining,
                )
                if return_code != 0:
                    operational_error = ErrorInfo(
                        code="boltzgen-task-failed",
                        message=(
                            f"BoltzGen exited with code {return_code}; "
                            f"collected {len(new_candidates)}/{remaining} complete candidates."
                        ),
                        retryable=True,
                    )
                elif len(new_candidates) != remaining:
                    operational_error = ErrorInfo(
                        code="incomplete-candidate-output",
                        message=(
                            f"BoltzGen returned zero but only produced "
                            f"{len(new_candidates)}/{remaining} complete candidates."
                        ),
                        retryable=True,
                    )
            except Exception as error:  # persisted as structured operational evidence
                ended = datetime.now(UTC)
                operational_error = ErrorInfo(
                    code="boltzgen-execution-error",
                    message=str(error)[:4096] or error.__class__.__name__,
                    retryable=True,
                )
            with lock:
                candidates.extend(new_candidates)
                candidate_ids = (
                    *task.candidate_ids,
                    *(item.candidate_id for item in new_candidates),
                )
                total = len(candidate_ids)
                succeeded = (
                    operational_error is None
                    and return_code == 0
                    and total == task.requested_candidates
                )
                final_attempt = running_attempt.model_copy(
                    update={
                        "status": (TaskStatus.SUCCEEDED if succeeded else TaskStatus.FAILED),
                        "collected_candidates": len(new_candidates),
                        "ended_at": ended,
                        "return_code": return_code,
                        "error": None if succeeded else operational_error,
                    }
                )
                next_status = (
                    TaskStatus.SUCCEEDED
                    if succeeded
                    else (
                        TaskStatus.PENDING
                        if total < task.requested_candidates
                        else TaskStatus.FAILED
                    )
                )
                task = task.model_copy(
                    update={
                        "status": next_status,
                        "collected_candidates": total,
                        "candidate_ids": candidate_ids,
                        "attempts": (*task.attempts[:-1], final_attempt),
                        "current_device": None,
                    }
                )
                tasks[task.task_id] = task
                if operational_error is not None:
                    recent_errors.append(
                        f"{task.task_id}: {operational_error.code}: {operational_error.message}"
                    )
                append_event(
                    event_type=("task-succeeded" if succeeded else "task-attempt-failed"),
                    message=(
                        f"Collected {len(new_candidates)} in attempt; "
                        f"strategy total {total}/{task.requested_candidates}."
                    ),
                    task=task,
                    attempt_number=attempt_number,
                    device=device,
                    from_status=TaskStatus.RUNNING,
                    to_status=next_status,
                    error=operational_error,
                )
                _json_payload(
                    task_attempt_root / "collection-report.json",
                    {
                        "schema_version": "0.1",
                        "task_id": task.task_id,
                        "strategy_id": task.strategy_id,
                        "task_attempt_number": attempt_number,
                        "requested_candidates": remaining,
                        "complete_candidates": len(new_candidates),
                        "candidate_ids": [item.candidate_id for item in new_candidates],
                        "return_code": return_code,
                        "status": str(final_attempt.status),
                        "error": (
                            None
                            if operational_error is None
                            else operational_error.model_dump(mode="json")
                        ),
                    },
                )
                persist("running")
            if task.status in {TaskStatus.SUCCEEDED, TaskStatus.FAILED}:
                break
        if task.status is TaskStatus.PENDING:
            exhausted_error = ErrorInfo(
                code="task-attempt-budget-exhausted",
                message=(
                    f"Task invocation exhausted {config.executor.max_task_attempts} "
                    f"attempts with {task.collected_candidates}/"
                    f"{task.requested_candidates} complete candidates."
                ),
                retryable=True,
            )
            with lock:
                recent_errors.append(f"{task.task_id}: {exhausted_error.message}")
                task = task.model_copy(update={"status": TaskStatus.FAILED})
                tasks[task.task_id] = task
                append_event(
                    event_type="task-incomplete",
                    message=exhausted_error.message,
                    task=task,
                    from_status=TaskStatus.PENDING,
                    to_status=TaskStatus.FAILED,
                    error=exhausted_error,
                )
                persist("incomplete")
        return task

    pending_plans = tuple(
        item for item in plan.strategies if tasks[item.task_id].status is not TaskStatus.SUCCEEDED
    )
    # Failed tasks from a previous invocation are explicitly reopened for resume.
    with lock:
        for item in pending_plans:
            task = tasks[item.task_id]
            if (
                task.status is TaskStatus.FAILED
                and task.collected_candidates < task.requested_candidates
            ):
                tasks[item.task_id] = task.model_copy(update={"status": TaskStatus.PENDING})
        persist("running")
    execute_on_devices(
        pending_plans,
        devices=config.executor.devices,
        worker=execute_task,
    )

    final_tasks = ordered_tasks()
    if any(task.status is not TaskStatus.SUCCEEDED for task in final_tasks):
        persist("incomplete")
        return Stage04Execution(
            status="incomplete",
            run_root=root,
            run_manifest=upstream.run_manifest_path,
            strategy_count=len(plan.strategies),
            complete_candidate_count=len(candidates),
        )

    ordered_candidates = tuple(
        sorted(
            candidates,
            key=lambda item: (item.strategy_id, item.ordinal_within_strategy),
        )
    )
    candidate_index = CandidateIndex(
        generated_at=datetime.now(UTC),
        strategy_bundle_sha256=upstream.strategy_bundle_ref.sha256,
        required_per_strategy=config.required_complete_candidates_per_strategy,
        candidates=ordered_candidates,
    )
    candidate_index_path = artifacts / "candidate-index.json"
    dump_model(candidate_index, candidate_index_path)
    task_table_path = artifacts / "task-table.json"
    dump_model(
        TaskTable(generated_at=datetime.now(UTC), tasks=final_tasks),
        task_table_path,
    )
    progress_final = _snapshot(
        tasks=final_tasks,
        updated_at=datetime.now(UTC),
        started_monotonic=started_monotonic,
        planned_candidates=planned_candidates,
        status="succeeded",
        recent_errors=tuple(recent_errors),
    )
    progress_final_path = artifacts / "progress-final.json"
    dump_model(progress_final, progress_final_path)
    events_artifact = artifacts / "task-events.jsonl"
    shutil.copyfile(events_path, events_artifact)

    output_refs = (
        _artifact(
            root,
            plan_path,
            artifact_id="pilot-plan",
            role="pilot-execution-plan",
            file_format="json",
        ),
        _artifact(
            root,
            task_table_path,
            artifact_id="pilot-task-table",
            role="task-terminal-records",
            file_format="json",
        ),
        _artifact(
            root,
            candidate_index_path,
            artifact_id="candidate-index",
            role="stage05-candidate-input",
            file_format="json",
        ),
        _artifact(
            root,
            progress_final_path,
            artifact_id="pilot-progress-final",
            role="terminal-progress",
            file_format="json",
        ),
        _artifact(
            root,
            events_artifact,
            artifact_id="pilot-task-events",
            role="append-only-task-events",
            file_format="jsonl",
        ),
        _artifact(
            root,
            backend_environment_path,
            artifact_id="pilot-backend-environment",
            role="backend-environment",
            file_format="json",
        ),
    )
    pilot_bundle_path = artifacts / "pilot-bundle.json"
    bundle = PilotBundle(
        generated_at=datetime.now(UTC),
        strategy_bundle=upstream.strategy_bundle_ref,
        pilot_plan=output_refs[0],
        task_table=output_refs[1],
        candidate_index=output_refs[2],
        progress_final=output_refs[3],
        task_events=output_refs[4],
        backend_environment=output_refs[5],
        strategy_count=len(plan.strategies),
        complete_candidate_count=len(ordered_candidates),
        complete_candidates_per_strategy=(config.required_complete_candidates_per_strategy),
    )
    dump_model(bundle, pilot_bundle_path)
    pilot_bundle_ref = _artifact(
        root,
        pilot_bundle_path,
        artifact_id="pilot-bundle",
        role="stage05-pilot-input",
        file_format="json",
    )
    wall_clock_end = datetime.now(UTC)
    ended_at = (
        wall_clock_end
        if wall_clock_end >= created_at
        else created_at + timedelta(microseconds=1)
    )
    task_log_refs: list[ArtifactRef] = []
    for task in final_tasks:
        for task_attempt in task.attempts:
            task_root = (
                attempt_root / "tasks" / task.task_id / f"attempt-{task_attempt.attempt_number:04d}"
            )
            for suffix, file_format in (("stdout", "text"), ("stderr", "text")):
                log_path = task_root / f"{suffix}.log"
                if log_path.is_file():
                    task_log_refs.append(
                        _artifact(
                            root,
                            log_path,
                            artifact_id=(
                                f"{task.task_id}-attempt-{task_attempt.attempt_number:04d}-{suffix}"
                            ),
                            role="backend-log",
                            file_format=file_format,
                        )
                    )
    attempt = Attempt(
        attempt_id=attempt_id,
        status=ExecutionStatus.SUCCEEDED,
        created_at=created_at,
        started_at=created_at,
        ended_at=ended_at,
        backend_name="boltzgen",
        backend_version="0.3.2",
        executor_name="local-multi-gpu",
        log_artifacts=tuple(task_log_refs),
    )
    dump_model(attempt, attempt_root / "attempt-manifest.json")
    stage_manifest = StageManifest(
        stage_id=StageId.PILOT_GENERATION,
        contract_version="0.1",
        status=ExecutionStatus.SUCCEEDED,
        created_at=created_at,
        completed_at=ended_at,
        input_artifacts=(upstream.strategy_bundle_ref,),
        output_artifacts=(*output_refs, pilot_bundle_ref),
        attempts=(attempt,),
        selected_attempt_id=attempt_id,
        warnings=(
            "Stage 04 candidate completeness is not a scientific filter pass.",
            "BoltzGen 0.3.2 does not expose a reliable deterministic generation seed.",
        ),
    )
    stage_manifest.validate_inputs_declared_by((upstream.stage03,))
    stage_manifest_path = artifacts / "stage-manifest.json"
    dump_model(stage_manifest, stage_manifest_path)
    stage_ref = _artifact(
        root,
        stage_manifest_path,
        artifact_id="stage-04-manifest",
        role="stage-manifest",
        file_format="json",
    )
    timestamp = (
        ended_at
        if ended_at > upstream.run.updated_at
        else upstream.run.updated_at + timedelta(microseconds=1)
    )
    terminal = resolved.stop_after_stage == 4
    next_run = upstream.run.next_revision(
        updated_at=timestamp,
        status=ExecutionStatus.SUCCEEDED if terminal else ExecutionStatus.RUNNING,
        completed_at=timestamp if terminal else None,
        stage_manifest_refs=(*upstream.run.stage_manifest_refs, stage_ref),
        clear_workflow_state=True,
    )
    run_manifest_path = root / "manifests" / f"run-manifest.v{next_run.revision:04d}.json"
    dump_model(next_run, run_manifest_path)
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
                notes=(f"Stage 04 collected {len(ordered_candidates)} complete candidates.",),
            ),
        ),
        generated_at=timestamp,
    )
    return Stage04Execution(
        status="succeeded",
        run_root=root,
        run_manifest=run_manifest_path,
        stage_manifest=stage_manifest_path,
        pilot_bundle=pilot_bundle_path,
        strategy_count=len(plan.strategies),
        complete_candidate_count=len(ordered_candidates),
    )


def read_stage04_progress(run_root: Path) -> ProgressSnapshot:
    path = (
        run_root.resolve()
        / str(StageId.PILOT_GENERATION)
        / "attempt-0001"
        / "runtime"
        / "progress.json"
    )
    return load_model(path, ProgressSnapshot)
