"""把早期 Stage 01 运行整体迁移到正式、开发和归档分区。"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from easydesign.orchestration import (
    RunIndexEntry,
    RunMovePlan,
    migrate_run_directories,
)
from easydesign.workspace_context import WorkspaceContext

ROOT = Path(__file__).resolve().parents[1]
RUNS_ROOT = WorkspaceContext.from_root(ROOT).runs_root


def main() -> None:
    moved_at = datetime.now(UTC)
    manifest = migrate_run_directories(
        runs_root=RUNS_ROOT,
        migration_relative_path="_archive/migrations/20260724-stage01-layout.json",
        migration_id="20260724-stage01-layout",
        moved_at=moved_at,
        plans=(
            RunMovePlan(
                source="apoe-protenix-bootstrap/no-msa-smoke",
                destination="_development/protenix-v2/apoe-no-msa-smoke-20260724",
                classification="backend-qualification",
            ),
            RunMovePlan(
                source="apoe-protenix-bootstrap/remote-msa-no-template",
                destination="_development/msa-services/apoe-remote-no-template-20260724",
                classification="external-service-diagnostic",
            ),
            RunMovePlan(
                source="apoe-stage01-adapter/run-20260724-no-msa",
                destination="apoe/20260724-001-stage01-no-msa",
                classification="project-run-legacy-layout",
            ),
        ),
        index_entries=(
            RunIndexEntry(
                category="development",
                path="_development/protenix-v2/apoe-no-msa-smoke-20260724",
                layout_version="legacy-0",
                status="succeeded",
                notes=("Protenix-v2 no-MSA backend qualification; not a project run.",),
            ),
            RunIndexEntry(
                category="development",
                path="_development/msa-services/apoe-remote-no-template-20260724",
                layout_version="legacy-0",
                status="failed-retryable",
                notes=("Two remote MSA diagnostics; neither produced an MSA artifact.",),
            ),
            RunIndexEntry(
                category="project-run",
                path="apoe/20260724-001-stage01-no-msa",
                layout_version="legacy-0",
                status="stage01-succeeded",
                project_id="apoe",
                run_id="20260724-001-stage01-no-msa",
                notes=("Historical no-MSA Target Bundle; internal layout remains immutable.",),
            ),
        ),
    )
    print(f"迁移完成或已验证: {manifest.migration_id}")
    for move in manifest.moves:
        print(
            f"{move.source} -> {move.destination} "
            f"files={move.fingerprint.file_count} sha256={move.fingerprint.sha256}"
        )


if __name__ == "__main__":
    main()
