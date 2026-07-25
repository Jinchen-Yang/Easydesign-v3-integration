from __future__ import annotations

from datetime import UTC, datetime

import pytest

from easydesign.core import (
    ErrorInfo,
    ProgressSnapshot,
    TaskAttemptRecord,
    TaskEvent,
    TaskRecord,
    TaskStatus,
)

NOW = datetime(2026, 7, 26, 2, 0, tzinfo=UTC)


def _succeeded_attempt(number: int = 1, count: int = 2) -> TaskAttemptRecord:
    return TaskAttemptRecord(
        attempt_number=number,
        status=TaskStatus.SUCCEEDED,
        requested_candidates=count,
        collected_candidates=count,
        device=0,
        command_sha256="a" * 64,
        output_relative_path=f"tasks/task/attempt-{number:04d}/backend-output",
        started_at=NOW,
        ended_at=NOW,
        return_code=0,
    )


def test_task_record_requires_exact_candidate_budget_for_success() -> None:
    task = TaskRecord(
        task_id="pilot-region-one",
        strategy_id="region-one",
        status=TaskStatus.SUCCEEDED,
        requested_candidates=2,
        collected_candidates=2,
        candidate_ids=("candidate-1", "candidate-2"),
        attempts=(_succeeded_attempt(),),
    )

    assert task.status is TaskStatus.SUCCEEDED
    with pytest.raises(ValueError, match="精确候选预算"):
        TaskRecord(
            task_id="pilot-region-one",
            strategy_id="region-one",
            status=TaskStatus.SUCCEEDED,
            requested_candidates=3,
            collected_candidates=2,
            candidate_ids=("candidate-1", "candidate-2"),
            attempts=(_succeeded_attempt(),),
        )


def test_failed_task_attempt_requires_structured_error() -> None:
    with pytest.raises(ValueError, match="结构化错误"):
        TaskAttemptRecord(
            attempt_number=1,
            status=TaskStatus.FAILED,
            requested_candidates=2,
            device=0,
            command_sha256="a" * 64,
            output_relative_path="output",
            started_at=NOW,
            ended_at=NOW,
            return_code=1,
        )

    attempt = TaskAttemptRecord(
        attempt_number=1,
        status=TaskStatus.FAILED,
        requested_candidates=2,
        collected_candidates=1,
        device=0,
        command_sha256="a" * 64,
        output_relative_path="output",
        started_at=NOW,
        ended_at=NOW,
        return_code=1,
        error=ErrorInfo(
            code="backend-failed",
            message="backend returned non-zero",
            retryable=True,
        ),
    )
    assert attempt.collected_candidates == 1


def test_progress_counts_and_event_sequence_are_typed() -> None:
    progress = ProgressSnapshot(
        stage_id="04-pilot-generation",
        updated_at=NOW,
        status="running",
        total_tasks=2,
        pending_tasks=1,
        waiting_tasks=0,
        running_tasks=1,
        succeeded_tasks=0,
        failed_tasks=0,
        planned_candidates=80,
        collected_candidates=20,
        per_device={"0": "region-one"},
    )
    event = TaskEvent(
        sequence=1,
        occurred_at=NOW,
        event_type="task-started",
        task_id="pilot-region-one",
        strategy_id="region-one",
        task_attempt_number=1,
        device=0,
        to_status=TaskStatus.RUNNING,
        message="started",
    )

    assert progress.running_tasks == 1
    assert event.sequence == 1
    with pytest.raises(ValueError, match="状态计数"):
        ProgressSnapshot(
            stage_id="04-pilot-generation",
            updated_at=NOW,
            status="running",
            total_tasks=3,
            pending_tasks=1,
            waiting_tasks=0,
            running_tasks=1,
            succeeded_tasks=0,
            failed_tasks=0,
            planned_candidates=80,
            collected_candidates=20,
        )
