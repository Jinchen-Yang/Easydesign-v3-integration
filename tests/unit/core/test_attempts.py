from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from pydantic import ValidationError

from easydesign.core import Attempt, ErrorInfo, ExecutionStatus


def test_pending_attempt_has_no_execution_times(now) -> None:
    attempt = Attempt(
        attempt_id="attempt-0001",
        status=ExecutionStatus.PENDING,
        created_at=now,
        backend_name="boltzgen",
        executor_name="local",
    )
    assert attempt.status.is_terminal is False


def test_failed_attempt_requires_error(now) -> None:
    with pytest.raises(ValidationError, match="error"):
        Attempt(
            attempt_id="attempt-0001",
            status=ExecutionStatus.FAILED,
            created_at=now,
            started_at=now,
            ended_at=now,
            backend_name="boltzgen",
            executor_name="local",
        )


def test_failed_attempt_records_typed_error(now) -> None:
    attempt = Attempt(
        attempt_id="attempt-0001",
        status=ExecutionStatus.FAILED,
        created_at=now,
        started_at=now,
        ended_at=now,
        backend_name="boltzgen",
        executor_name="local",
        error=ErrorInfo(code="cuda-oom", message="out of memory", retryable=True),
    )
    assert attempt.status.is_terminal
    assert attempt.error is not None
    assert attempt.error.retryable


def test_running_attempt_cannot_have_end_time(now) -> None:
    with pytest.raises(ValidationError, match="running"):
        Attempt(
            attempt_id="attempt-0001",
            status=ExecutionStatus.RUNNING,
            created_at=now,
            started_at=now,
            ended_at=now,
            backend_name="boltzgen",
            executor_name="local",
        )


def test_attempt_cannot_start_before_creation(now) -> None:
    with pytest.raises(ValidationError, match="开始时间"):
        Attempt(
            attempt_id="attempt-0001",
            status=ExecutionStatus.RUNNING,
            created_at=now,
            started_at=now - timedelta(seconds=1),
            backend_name="boltzgen",
            executor_name="local",
        )


def test_attempt_rejects_naive_datetime() -> None:
    with pytest.raises(ValidationError, match="时区"):
        Attempt(
            attempt_id="attempt-0001",
            status=ExecutionStatus.PENDING,
            created_at=datetime(2026, 7, 24, 8, 0),
            backend_name="boltzgen",
            executor_name="local",
        )


def test_terminal_attempt_is_frozen(succeeded_attempt) -> None:
    with pytest.raises(ValidationError, match="frozen"):
        succeeded_attempt.status = ExecutionStatus.FAILED
