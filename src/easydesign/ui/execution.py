"""Stage 04/06 的 manifest-only 历史和结构化实时执行投影。"""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

from easydesign.core import (
    ManifestStateError,
    ProgressSnapshot,
    RunManifest,
    StageManifest,
    TaskEvent,
    TaskRecord,
    TaskStatus,
    load_model,
)

from .models import (
    DeviceExecutionProjection,
    ExecutionProgressProjection,
    StrategyExecutionProjection,
    TaskExecutionProjection,
)
from .projections import _latest_run_manifest

_STAGE_CONTRACTS = {
    4: {
        "stage_id": "04-pilot-generation",
        "progress": "pilot-progress-final",
        "tasks": "pilot-task-table",
        "events": "pilot-task-events",
    },
    6: {
        "stage_id": "06-scale-generation-and-refolding",
        "progress": "scale-progress-final",
        "tasks": "scale-task-table",
        "events": "scale-task-events",
    },
}


def _read_task_table(path: Path) -> tuple[TaskRecord, ...]:
    value = json.loads(path.read_text(encoding="utf-8"))
    rows = value.get("tasks") if isinstance(value, dict) else None
    if not isinstance(rows, list):
        raise ManifestStateError("执行任务表必须包含 tasks 列表")
    return tuple(TaskRecord.model_validate(item) for item in rows)


def _read_events(path: Path) -> tuple[TaskEvent, ...]:
    events: list[TaskEvent] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            text = line.strip()
            if text:
                events.append(TaskEvent.model_validate_json(text))
    return tuple(events)


def _runtime_paths(run_root: Path, stage_id: str) -> tuple[Path, Path]:
    runtime = run_root / stage_id / "attempt-0001" / "runtime"
    state_name = (
        "scale-state.json"
        if stage_id == "06-scale-generation-and-refolding"
        else "task-state.json"
    )
    return runtime / state_name, runtime / "task-events.jsonl"


def _stage_manifest(
    run_root: Path,
    run: RunManifest,
    stage_id: str,
) -> StageManifest | None:
    reference = next(
        (item for item in run.stage_manifest_refs if item.producer_stage == stage_id),
        None,
    )
    return None if reference is None else load_model(reference.verify(run_root), StageManifest)


def _load_execution_sources(
    run_root: Path,
    stage_number: int,
    *,
    runtime_snapshot: ProgressSnapshot | None,
) -> tuple[ProgressSnapshot, tuple[TaskRecord, ...], tuple[TaskEvent, ...]]:
    contract = _STAGE_CONTRACTS.get(stage_number)
    if contract is None:
        raise ValueError("执行投影只支持 Stage 04 或 Stage 06")
    run, _ = _latest_run_manifest(run_root)
    stage = _stage_manifest(run_root, run, contract["stage_id"])
    if stage is not None:
        progress = load_model(
            stage.require_output(contract["progress"]).verify(run_root),
            ProgressSnapshot,
        )
        artifact_map = {item.artifact_id: item for item in stage.output_artifacts}
        task_ref = artifact_map.get(contract["tasks"])
        event_ref = artifact_map.get(contract["events"])
        tasks = () if task_ref is None else _read_task_table(task_ref.verify(run_root))
        events = () if event_ref is None else _read_events(event_ref.verify(run_root))
        return progress, tasks, events
    if runtime_snapshot is None or runtime_snapshot.stage_id != contract["stage_id"]:
        raise ManifestStateError(f"当前运行没有可读取的 {contract['stage_id']} 执行记录")
    task_path, event_path = _runtime_paths(run_root, contract["stage_id"])
    tasks = _read_task_table(task_path) if task_path.is_file() else ()
    events = _read_events(event_path) if event_path.is_file() else ()
    return runtime_snapshot, tasks, events


def _duration_seconds(started_at: datetime, ended_at: datetime | None, now: datetime) -> float:
    end = now if ended_at is None else ended_at
    return max(0.0, (end - started_at).total_seconds())


def _task_projection(
    task: TaskRecord,
    snapshot: ProgressSnapshot,
) -> TaskExecutionProjection:
    last_device = task.current_device
    if last_device is None and task.attempts:
        last_device = task.attempts[-1].device
    heartbeat = next(
        (item for item in snapshot.task_heartbeats if item.task_id == task.task_id),
        None,
    )
    return TaskExecutionProjection(
        task_id=task.task_id,
        strategy_id=task.strategy_id,
        status=str(task.status),
        requested_candidates=task.requested_candidates,
        collected_candidates=task.collected_candidates,
        attempt_count=len(task.attempts),
        retry_count=max(0, len(task.attempts) - 1),
        last_device=last_device,
        latest_heartbeat_at=None if heartbeat is None else heartbeat.updated_at,
        heartbeat_elapsed_seconds=(
            None if heartbeat is None else heartbeat.elapsed_seconds
        ),
        heartbeat_message=None if heartbeat is None else heartbeat.message,
    )


def _device_projections(
    tasks: tuple[TaskRecord, ...],
    snapshot: ProgressSnapshot,
) -> tuple[DeviceExecutionProjection, ...]:
    now = datetime.now(tz=UTC)
    device_tasks: dict[int, dict[str, TaskRecord]] = defaultdict(dict)
    attempt_count: dict[int, int] = defaultdict(int)
    failed_attempt_count: dict[int, int] = defaultdict(int)
    busy_seconds: dict[int, float] = defaultdict(float)
    current: dict[int, TaskRecord] = {}
    for task in tasks:
        for attempt in task.attempts:
            device_tasks[attempt.device][task.task_id] = task
            attempt_count[attempt.device] += 1
            failed_attempt_count[attempt.device] += int(attempt.status is TaskStatus.FAILED)
            busy_seconds[attempt.device] += _duration_seconds(
                attempt.started_at,
                attempt.ended_at,
                now,
            )
        if task.current_device is not None:
            current[task.current_device] = task
    for device_text, strategy_id in snapshot.per_device.items():
        if strategy_id is None:
            continue
        try:
            device = int(device_text)
        except ValueError as error:
            raise ManifestStateError(f"无效设备编号: {device_text}") from error
        if device not in current:
            matching = next(
                (task for task in tasks if task.strategy_id == strategy_id),
                None,
            )
            if matching is not None:
                current[device] = matching
    devices = sorted(set(device_tasks) | set(current))
    rows: list[DeviceExecutionProjection] = []
    for device in devices:
        assigned = tuple(
            sorted(device_tasks.get(device, {}).values(), key=lambda item: item.task_id)
        )
        succeeded = tuple(
            task
            for task in assigned
            if task.status is TaskStatus.SUCCEEDED
            and task.attempts
            and task.attempts[-1].device == device
        )
        active = current.get(device)
        active_heartbeat = next(
            (
                item
                for item in snapshot.task_heartbeats
                if active is not None and item.task_id == active.task_id
            ),
            None,
        )
        rows.append(
            DeviceExecutionProjection(
                device=device,
                current_task_id=None if active is None else active.task_id,
                current_strategy_id=None if active is None else active.strategy_id,
                assigned_task_count=len(assigned),
                succeeded_task_count=len(succeeded),
                attempt_count=attempt_count[device],
                failed_attempt_count=failed_attempt_count[device],
                collected_candidates=sum(task.collected_candidates for task in succeeded),
                busy_seconds=busy_seconds[device],
                latest_heartbeat_at=(
                    None if active_heartbeat is None else active_heartbeat.updated_at
                ),
                heartbeat_elapsed_seconds=(
                    None if active_heartbeat is None else active_heartbeat.elapsed_seconds
                ),
                heartbeat_message=(
                    None if active_heartbeat is None else active_heartbeat.message
                ),
                tasks=tuple(_task_projection(task, snapshot) for task in assigned),
            )
        )
    return tuple(rows)


def get_execution_progress(
    run_root: Path,
    stage_number: int,
    *,
    runtime_snapshot: ProgressSnapshot | None = None,
) -> ExecutionProgressProjection:
    """读取 Stage 04/06 的终态证据，或显式 runtime snapshot 对应的活动记录。"""

    root = run_root.resolve()
    progress, tasks, events = _load_execution_sources(
        root,
        stage_number,
        runtime_snapshot=runtime_snapshot,
    )
    devices = _device_projections(tasks, progress)
    strategy_tasks: dict[str, list[TaskRecord]] = defaultdict(list)
    for task in tasks:
        strategy_tasks[task.strategy_id].append(task)
    strategies = tuple(
        StrategyExecutionProjection(
            strategy_id=strategy_id,
            task_count=len(rows),
            succeeded_task_count=sum(
                item.status is TaskStatus.SUCCEEDED for item in rows
            ),
            failed_task_count=sum(
                item.status is TaskStatus.FAILED for item in rows
            ),
            requested_candidates=sum(item.requested_candidates for item in rows),
            collected_candidates=sum(item.collected_candidates for item in rows),
        )
        for strategy_id, rows in sorted(strategy_tasks.items())
    )
    return ExecutionProgressProjection(
        stage_number=stage_number,
        stage_id=progress.stage_id,
        status=progress.status,
        updated_at=progress.updated_at,
        total_tasks=progress.total_tasks,
        pending_tasks=progress.pending_tasks,
        waiting_tasks=progress.waiting_tasks,
        running_tasks=progress.running_tasks,
        succeeded_tasks=progress.succeeded_tasks,
        failed_tasks=progress.failed_tasks,
        planned_candidates=progress.planned_candidates,
        collected_candidates=progress.collected_candidates,
        elapsed_seconds=progress.elapsed_seconds,
        throughput_candidates_per_hour=progress.throughput_candidates_per_hour,
        estimated_remaining_seconds=progress.estimated_remaining_seconds,
        device_history_status="available" if devices else "not-recorded",
        devices=devices,
        strategies=strategies,
        recent_events=tuple(
            {
                "sequence": event.sequence,
                "occurred_at": event.occurred_at.isoformat(),
                "event_type": event.event_type,
                "task_id": event.task_id,
                "strategy_id": event.strategy_id,
                "device": event.device,
                "message": event.message,
                "error": None if event.error is None else event.error.model_dump(mode="json"),
            }
            for event in events[-20:]
        ),
        recent_errors=progress.recent_errors,
    )


__all__ = ["get_execution_progress"]
