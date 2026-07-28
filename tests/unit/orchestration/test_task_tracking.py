from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from easydesign.core import ManifestStateError, ProgressSnapshot, TaskEvent
from easydesign.orchestration.task_tracking import (
    TaskEventJournal,
    atomic_dump_runtime_model,
    load_latest_runtime_model,
)


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


def test_runtime_snapshot_reads_highest_valid_revision(tmp_path: Path) -> None:
    path = tmp_path / "progress.json"
    first = ProgressSnapshot(
        stage_id="04-pilot-generation",
        updated_at=datetime(2026, 7, 26, 2, 0, tzinfo=UTC),
        status="running",
        total_tasks=1,
        pending_tasks=1,
        waiting_tasks=0,
        running_tasks=0,
        succeeded_tasks=0,
        failed_tasks=0,
        planned_candidates=1,
        collected_candidates=0,
    )
    second = first.model_copy(
        update={
            "pending_tasks": 0,
            "succeeded_tasks": 1,
            "collected_candidates": 1,
            "status": "succeeded",
        }
    )
    atomic_dump_runtime_model(first, path)
    atomic_dump_runtime_model(second, path)
    corrupt = path.with_name("progress.json.revisions") / "revision-00000002.json"
    corrupt.write_text("{broken", encoding="utf-8")

    loaded = load_latest_runtime_model(path, ProgressSnapshot)

    assert loaded.status == "succeeded"
    assert loaded.collected_candidates == 1
