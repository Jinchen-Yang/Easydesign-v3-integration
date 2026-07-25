from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from easydesign.core import ManifestStateError, TaskEvent
from easydesign.orchestration.task_tracking import TaskEventJournal


def _event(sequence: int) -> TaskEvent:
    return TaskEvent(
        sequence=sequence,
        occurred_at=datetime(2026, 7, 26, 2, 0, tzinfo=UTC),
        event_type="task-started",
        message="test",
    )


def test_event_journal_is_append_only_and_sequence_checked(tmp_path: Path) -> None:
    path = tmp_path / "task-events.jsonl"
    journal = TaskEventJournal(path)
    journal.append(_event(1))
    journal.append(_event(2))

    reopened = TaskEventJournal(path)
    assert reopened.next_sequence == 3
    with pytest.raises(ManifestStateError, match="应为 3"):
        reopened.append(_event(4))
    assert len(path.read_text(encoding="utf-8").splitlines()) == 2
