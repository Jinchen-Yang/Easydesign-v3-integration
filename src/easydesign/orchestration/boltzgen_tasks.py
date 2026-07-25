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
    BoltzGenGenerationRequest,
)
from easydesign.core import (
    ErrorInfo,
    TaskAttemptRecord,
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
    ordinal_offset: int = 0,
) -> TaskRecord:
    """Run exact deficits with immutable attempts and strict candidate collection."""

    current = task
    attempts_this_invocation = 0
    while (
        current.collected_candidates < current.requested_candidates
        and attempts_this_invocation < maximum_attempts_this_invocation
    ):
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
            result = adapter.execute(request)
            return_code = result.return_code
            ended_at = result.ended_at
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
            operational_error is None
            and return_code == 0
            and total == current.requested_candidates
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
            else (
                TaskStatus.PENDING
                if total < current.requested_candidates
                else TaskStatus.FAILED
            )
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
                event_type=(
                    "task-succeeded" if succeeded else "task-attempt-failed"
                ),
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
