"""Reusable immutable-attempt execution for one BoltzGen candidate task."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from easydesign.backends.boltzgen import (
    BoltzGenGenerationAdapter,
    BoltzGenGenerationHeartbeat,
    BoltzGenGenerationRequest,
)
from easydesign.core import (
    ErrorInfo,
    ManifestStateError,
    TaskAttemptRecord,
    TaskHeartbeat,
    TaskRecord,
    TaskStatus,
)
from easydesign.stages.s04_pilot_generation import (
    CandidateRecord,
    collect_boltzgen_candidates,
)


@dataclass(frozen=True, slots=True)
class TaskTransition:
    event_type: str
    message: str
    task: TaskRecord
    new_candidates: tuple[CandidateRecord, ...] = ()
    attempt_number: int | None = None
    device: int | None = None
    from_status: TaskStatus | None = None
    to_status: TaskStatus | None = None
    error: ErrorInfo | None = None


TaskTransitionCallback = Callable[[TaskTransition], None]
TaskHeartbeatCallback = Callable[[TaskHeartbeat], None]


def _command_sha256(command: tuple[str, ...]) -> str:
    payload = json.dumps(command, ensure_ascii=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _write_collection_report(
    *,
    path: Path,
    task: TaskRecord,
    attempt_number: int,
    requested_candidates: int,
    candidates: tuple[CandidateRecord, ...],
    return_code: int,
    status: TaskStatus,
    error: ErrorInfo | None,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as handle:
        json.dump(
            {
                "schema_version": "0.1",
                "task_id": task.task_id,
                "strategy_id": task.strategy_id,
                "task_attempt_number": attempt_number,
                "requested_candidates": requested_candidates,
                "complete_candidates": len(candidates),
                "candidate_ids": [item.candidate_id for item in candidates],
                "return_code": return_code,
                "status": str(status),
                "error": None if error is None else error.model_dump(mode="json"),
            },
            handle,
            ensure_ascii=False,
            allow_nan=False,
            indent=2,
            sort_keys=True,
        )
        handle.write("\n")


def recover_interrupted_boltzgen_task(
    *,
    root: Path,
    task: TaskRecord,
    stage_attempt_id: str,
    producer_stage: str,
    ordinal_offset: int = 0,
) -> TaskTransition | None:
    """Salvage complete artifacts from a task left running by process interruption."""

    if task.status is not TaskStatus.RUNNING:
        return None
    running_attempt = task.attempts[-1]
    remaining = task.requested_candidates - task.collected_candidates
    salvaged = (
        collect_boltzgen_candidates(
            run_root=root,
            backend_output=root / running_attempt.output_relative_path,
            strategy_id=task.strategy_id,
            task_id=task.task_id,
            task_attempt_number=running_attempt.attempt_number,
            stage_attempt_id=stage_attempt_id,
            ordinal_start=ordinal_offset + task.collected_candidates + 1,
            maximum_candidates=max(remaining, 0),
            producer_stage=producer_stage,
        )
        if remaining > 0
        else ()
    )
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
    recovered = task.model_copy(
        update={
            "status": TaskStatus.PENDING,
            "collected_candidates": len(candidate_ids),
            "candidate_ids": candidate_ids,
            "attempts": (*task.attempts[:-1], closed_attempt),
            "current_device": None,
        }
    )
    return TaskTransition(
        event_type="task-interrupted",
        message="Recovered an interrupted task for resume.",
        task=recovered,
        new_candidates=salvaged,
        attempt_number=running_attempt.attempt_number,
        device=running_attempt.device,
        from_status=TaskStatus.RUNNING,
        to_status=TaskStatus.PENDING,
        error=error,
    )


def recover_completed_boltzgen_outputs(
    *,
    root: Path,
    task: TaskRecord,
    stage_attempt_id: str,
    producer_stage: str,
    ordinal_offset: int = 0,
) -> TaskTransition | None:
    """Revalidate successful backend outputs rejected by an older collector.

    A completed BoltzGen process can precede a deterministic collection failure. On
    resume, re-read only immutable, return-code-zero attempt outputs and preserve the
    original failed attempt/error record. This avoids recomputing a scientific product
    after a collector compatibility fix.
    """

    if task.status is TaskStatus.SUCCEEDED:
        return None
    remaining = task.requested_candidates - task.collected_candidates
    if remaining <= 0:
        return None
    attempts = list(task.attempts)
    recovery_attempts: list[TaskAttemptRecord] = []
    salvaged: list[CandidateRecord] = []
    for attempt in attempts:
        if (
            attempt.status is not TaskStatus.FAILED
            or attempt.return_code != 0
            or attempt.collected_candidates != 0
        ):
            continue
        try:
            recovered = collect_boltzgen_candidates(
                run_root=root,
                backend_output=root / attempt.output_relative_path,
                strategy_id=task.strategy_id,
                task_id=task.task_id,
                task_attempt_number=attempt.attempt_number,
                stage_attempt_id=stage_attempt_id,
                ordinal_start=ordinal_offset + task.collected_candidates + len(salvaged) + 1,
                maximum_candidates=remaining - len(salvaged),
                producer_stage=producer_stage,
            )
        except ManifestStateError:
            # The original terminal failure remains authoritative when the current
            # collector still cannot validate the immutable backend output.
            continue
        if not recovered:
            continue
        salvaged.extend(recovered)
        recovered_at = datetime.now(UTC)
        recovery_attempts.append(
            TaskAttemptRecord(
                attempt_number=len(attempts) + len(recovery_attempts) + 1,
                status=TaskStatus.SUCCEEDED,
                requested_candidates=len(recovered),
                collected_candidates=len(recovered),
                device=attempt.device,
                command_sha256=_command_sha256(
                    (
                        "recover-completed-output",
                        str(attempt.attempt_number),
                        attempt.output_relative_path,
                    )
                ),
                output_relative_path=attempt.output_relative_path,
                started_at=recovered_at,
                ended_at=recovered_at,
                return_code=0,
            )
        )
        if len(salvaged) >= remaining:
            break
    if not salvaged:
        return None
    candidate_ids = (*task.candidate_ids, *(item.candidate_id for item in salvaged))
    complete = len(candidate_ids) >= task.requested_candidates
    recovered_task = task.model_copy(
        update={
            "status": TaskStatus.SUCCEEDED if complete else TaskStatus.PENDING,
            "collected_candidates": len(candidate_ids),
            "candidate_ids": candidate_ids,
            "attempts": (*attempts, *recovery_attempts),
            "current_device": None,
        }
    )
    return TaskTransition(
        event_type="task-output-recovered",
        message=(
            f"Revalidated {len(salvaged)} candidate(s) from completed backend output."
        ),
        task=recovered_task,
        new_candidates=tuple(salvaged),
        attempt_number=recovery_attempts[-1].attempt_number,
        device=recovery_attempts[-1].device,
        from_status=task.status,
        to_status=recovered_task.status,
    )


def execute_boltzgen_candidate_task(
    *,
    root: Path,
    task: TaskRecord,
    design_specification: Path,
    task_root: Path,
    stage_attempt_id: str,
    producer_stage: str,
    adapter: BoltzGenGenerationAdapter,
    device: int,
    maximum_attempts_this_invocation: int,
    on_transition: TaskTransitionCallback,
    on_heartbeat: TaskHeartbeatCallback | None = None,
    should_stop: Callable[[], bool] | None = None,
    ordinal_offset: int = 0,
) -> TaskRecord:
    """Run exact deficits with immutable attempts and strict candidate collection."""

    current = task
    attempts_this_invocation = 0
    while (
        current.collected_candidates < current.requested_candidates
        and attempts_this_invocation < maximum_attempts_this_invocation
    ):
        if should_stop is not None and should_stop():
            break
        attempts_this_invocation += 1
        attempt_number = len(current.attempts) + 1
        remaining = current.requested_candidates - current.collected_candidates
        attempt_root = task_root / f"attempt-{attempt_number:04d}"
        request = BoltzGenGenerationRequest(
            design_specification=design_specification,
            output_directory=attempt_root / "backend-output",
            requested_candidates=remaining,
            physical_device=device,
            stdout_path=attempt_root / "stdout.log",
            stderr_path=attempt_root / "stderr.log",
        )
        command = adapter.build_command(request)
        started_at = datetime.now(UTC)
        running_attempt = TaskAttemptRecord(
            attempt_number=attempt_number,
            status=TaskStatus.RUNNING,
            requested_candidates=remaining,
            device=device,
            command_sha256=_command_sha256(command),
            output_relative_path=request.output_directory.relative_to(root).as_posix(),
            started_at=started_at,
        )
        previous_status = current.status
        current = current.model_copy(
            update={
                "status": TaskStatus.RUNNING,
                "attempts": (*current.attempts, running_attempt),
                "current_device": device,
            }
        )
        on_transition(
            TaskTransition(
                event_type="task-started",
                message=f"Requested {remaining} complete candidates.",
                task=current,
                attempt_number=attempt_number,
                device=device,
                from_status=previous_status,
                to_status=TaskStatus.RUNNING,
            )
        )

        operational_error: ErrorInfo | None = None
        return_code = 1
        ended_at = datetime.now(UTC)
        new_candidates: tuple[CandidateRecord, ...] = ()
        try:
            heartbeat_task_id = current.task_id
            heartbeat_strategy_id = current.strategy_id
            heartbeat_attempt_number = attempt_number

            def emit_heartbeat(
                value: BoltzGenGenerationHeartbeat,
                task_id: str = heartbeat_task_id,
                strategy_id: str = heartbeat_strategy_id,
                task_attempt_number: int = heartbeat_attempt_number,
            ) -> None:
                if on_heartbeat is None:
                    return
                on_heartbeat(
                    TaskHeartbeat(
                        task_id=task_id,
                        strategy_id=strategy_id,
                        device=device,
                        attempt_number=task_attempt_number,
                        phase=value.phase,
                        updated_at=value.observed_at,
                        elapsed_seconds=value.elapsed_seconds,
                        message=value.message,
                        completed=value.completed,
                        total=value.total,
                        step=value.step,
                        steps=value.steps,
                    )
                )

            result = (
                adapter.execute(request)
                if on_heartbeat is None
                else adapter.execute(request, heartbeat_callback=emit_heartbeat)
            )
            return_code = result.return_code
            # Adapter timestamps may be rounded, frozen in tests, or originate from a
            # backend clock that is marginally behind the orchestrator clock.  Runtime
            # task state must remain chronologically valid without rewriting backend
            # provenance stored by the adapter.
            ended_at = max(result.ended_at, started_at)
            new_candidates = collect_boltzgen_candidates(
                run_root=root,
                backend_output=result.output_directory,
                strategy_id=current.strategy_id,
                task_id=current.task_id,
                task_attempt_number=attempt_number,
                stage_attempt_id=stage_attempt_id,
                ordinal_start=ordinal_offset + current.collected_candidates + 1,
                maximum_candidates=remaining,
                producer_stage=producer_stage,
            )
            if return_code != 0:
                operational_error = ErrorInfo(
                    code="boltzgen-task-failed",
                    message=(
                        f"BoltzGen exited with code {return_code}; collected "
                        f"{len(new_candidates)}/{remaining} complete candidates."
                    ),
                    retryable=True,
                )
            elif len(new_candidates) != remaining:
                operational_error = ErrorInfo(
                    code="incomplete-candidate-output",
                    message=(
                        f"BoltzGen returned zero but produced "
                        f"{len(new_candidates)}/{remaining} complete candidates."
                    ),
                    retryable=True,
                )
        except Exception as error:
            ended_at = datetime.now(UTC)
            operational_error = ErrorInfo(
                code="boltzgen-execution-error",
                message=str(error)[:4096] or error.__class__.__name__,
                retryable=True,
            )

        candidate_ids = (
            *current.candidate_ids,
            *(item.candidate_id for item in new_candidates),
        )
        total = len(candidate_ids)
        succeeded = (
            operational_error is None and return_code == 0 and total == current.requested_candidates
        )
        final_attempt = running_attempt.model_copy(
            update={
                "status": TaskStatus.SUCCEEDED if succeeded else TaskStatus.FAILED,
                "collected_candidates": len(new_candidates),
                "ended_at": ended_at,
                "return_code": return_code,
                "error": None if succeeded else operational_error,
            }
        )
        next_status = (
            TaskStatus.SUCCEEDED
            if succeeded
            else (TaskStatus.PENDING if total < current.requested_candidates else TaskStatus.FAILED)
        )
        current = current.model_copy(
            update={
                "status": next_status,
                "collected_candidates": total,
                "candidate_ids": candidate_ids,
                "attempts": (*current.attempts[:-1], final_attempt),
                "current_device": None,
            }
        )
        _write_collection_report(
            path=attempt_root / "collection-report.json",
            task=current,
            attempt_number=attempt_number,
            requested_candidates=remaining,
            candidates=new_candidates,
            return_code=return_code,
            status=final_attempt.status,
            error=operational_error,
        )
        on_transition(
            TaskTransition(
                event_type=("task-succeeded" if succeeded else "task-attempt-failed"),
                message=(
                    f"Collected {len(new_candidates)} in attempt; strategy total "
                    f"{total}/{current.requested_candidates}."
                ),
                task=current,
                new_candidates=new_candidates,
                attempt_number=attempt_number,
                device=device,
                from_status=TaskStatus.RUNNING,
                to_status=next_status,
                error=operational_error,
            )
        )
        if current.status in {TaskStatus.SUCCEEDED, TaskStatus.FAILED}:
            break

    if current.status is TaskStatus.PENDING:
        exhausted_error = ErrorInfo(
            code="task-attempt-budget-exhausted",
            message=(
                f"Task invocation exhausted {maximum_attempts_this_invocation} attempts "
                f"with {current.collected_candidates}/"
                f"{current.requested_candidates} complete candidates."
            ),
            retryable=True,
        )
        current = current.model_copy(update={"status": TaskStatus.FAILED})
        on_transition(
            TaskTransition(
                event_type="task-incomplete",
                message=exhausted_error.message,
                task=current,
                from_status=TaskStatus.PENDING,
                to_status=TaskStatus.FAILED,
                error=exhausted_error,
            )
        )
    return current
