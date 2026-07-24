from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

from easydesign.core import load_model
from easydesign.orchestration import (
    RunIndex,
    RunIndexEntry,
    RunMovePlan,
    fingerprint_tree,
    migrate_run_directories,
)


def test_migration_moves_whole_tree_and_is_idempotent(tmp_path: Path) -> None:
    runs_root = tmp_path / "runs"
    source = runs_root / "old-project/run-old"
    artifact = source / "01-target-preparation/attempt-0001/artifacts/target.cif"
    artifact.parent.mkdir(parents=True)
    artifact.write_text("data_target\n", encoding="utf-8")
    digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
    bundle = artifact.parent / "target-bundle.json"
    bundle.write_text(
        json.dumps(
            {
                "target_structure": {
                    "relative_path": (
                        "01-target-preparation/attempt-0001/artifacts/target.cif"
                    ),
                    "sha256": digest,
                    "size_bytes": artifact.stat().st_size,
                }
            }
        ),
        encoding="utf-8",
    )
    before = fingerprint_tree(source)
    moved_at = datetime(2026, 7, 24, 8, 0, tzinfo=UTC)
    plan = RunMovePlan(
        source="old-project/run-old",
        destination="apoe/20260724-001",
        classification="project-run-legacy-layout",
    )
    entry = RunIndexEntry(
        category="project-run",
        path="apoe/20260724-001",
        layout_version="legacy-0",
        status="succeeded",
        project_id="apoe",
        run_id="20260724-001",
    )

    first = migrate_run_directories(
        runs_root=runs_root,
        migration_relative_path="_archive/migrations/test.json",
        migration_id="test",
        moved_at=moved_at,
        plans=(plan,),
        index_entries=(entry,),
    )
    destination = runs_root / "apoe/20260724-001"
    assert not source.exists()
    assert fingerprint_tree(destination) == before == first.moves[0].fingerprint
    assert load_model(runs_root / "run-index.json", RunIndex).entries == (entry,)

    second = migrate_run_directories(
        runs_root=runs_root,
        migration_relative_path="_archive/migrations/test.json",
        migration_id="test",
        moved_at=moved_at,
        plans=(plan,),
        index_entries=(entry,),
    )
    assert second == first
