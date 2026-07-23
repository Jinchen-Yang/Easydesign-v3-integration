from __future__ import annotations

from datetime import UTC, datetime

import pytest

from easydesign.core import Attempt, ExecutionStatus


@pytest.fixture
def now() -> datetime:
    return datetime(2026, 7, 24, 8, 0, tzinfo=UTC)


@pytest.fixture
def succeeded_attempt(now: datetime) -> Attempt:
    return Attempt(
        attempt_id="attempt-0001",
        status=ExecutionStatus.SUCCEEDED,
        created_at=now,
        started_at=now,
        ended_at=now,
        backend_name="unit-test",
        backend_version="1.0",
        executor_name="local",
        seed=7,
    )
