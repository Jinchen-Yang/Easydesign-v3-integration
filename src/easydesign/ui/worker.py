"""独立 UI worker：只调用公共 orchestration API。"""

from __future__ import annotations

import argparse
import hashlib
from datetime import UTC, datetime
from pathlib import Path

from easydesign.core import load_model
from easydesign.orchestration import (
    RunIndexEntry,
    execute_pipeline,
    select_project_primary_run,
    upsert_run_index_entries,
)
from easydesign.orchestration.application import (
    continue_pipeline_after_decision,
    resume_pipeline,
)
from easydesign.orchestration.task_tracking import atomic_dump_runtime_model

from .models import UiJobRecord
from .selftest import SelfTestStore
from .sessions import DesignSessionStore


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--job-record", type=Path, required=True)
    parser.add_argument("--operation", choices=("run", "resume", "decision"), required=True)
    parser.add_argument("--drain-file", type=Path, required=True)
    parser.add_argument("--config", type=Path)
    parser.add_argument("--run-root", type=Path)
    parser.add_argument("--decision-record", type=Path)
    parser.add_argument("--profile", type=Path)
    parser.add_argument("--runs-root", type=Path)
    parser.add_argument("--run-id")
    parser.add_argument("--continue-after-stage", type=int)
    parser.add_argument("--session-root", type=Path)
    parser.add_argument("--self-test-root", type=Path)
    parser.add_argument("--self-test-runs-root", type=Path)
    return parser


def _run_key(run_root: Path) -> str:
    return hashlib.sha256(str(run_root.resolve()).encode("utf-8")).hexdigest()[:24]


def _status_text(status: object) -> str:
    return str(getattr(status, "value", status))


def _publish_product_run_navigation(
    *,
    record: UiJobRecord,
    run_root: Path | None,
    runs_root: Path | None,
    project_id: str | None,
    status: object,
) -> str | None:
    """Make a completed UI continuation the project-visible current run.

    Run manifests remain the scientific source of truth; run-index and
    PROJECT.json are mutable navigation projections.  A stale projection should
    not make the UI fall back to the source run after the worker has already
    produced a verified continuation.
    """

    if record.operation != "run" or run_root is None or runs_root is None:
        return None
    selected_project = project_id or record.project_id
    if not selected_project:
        return "缺少 project_id，无法更新项目导航"
    try:
        root = runs_root.resolve()
        resolved_run = run_root.resolve()
        relative = resolved_run.relative_to(root).as_posix()
        run_id = resolved_run.name
        now = datetime.now(tz=UTC)
        stage_note = (
            f"UI job completed Stage {record.stage_number}; project navigation selected this run."
            if record.stage_number is not None
            else "UI job completed; project navigation selected this run."
        )
        upsert_run_index_entries(
            root,
            (
                RunIndexEntry(
                    category="project-run",
                    path=relative,
                    layout_version="1",
                    status=_status_text(status),
                    project_id=selected_project,
                    run_id=run_id,
                    notes=(stage_note,),
                ),
            ),
            generated_at=now,
        )
        select_project_primary_run(
            root,
            project_id=selected_project,
            run_id=run_id,
            changed_at=now,
        )
    except Exception as error:  # navigation is diagnostic; do not rewrite science status
        return str(error)[:4096] or error.__class__.__name__
    return None


def main() -> int:
    arguments = _parser().parse_args()
    record = load_model(arguments.job_record, UiJobRecord)
    try:
        if arguments.operation == "run":
            if arguments.config is None:
                raise ValueError("run worker 缺少 --config")
            outcome = execute_pipeline(
                arguments.config,
                profile_path=arguments.profile,
                runs_root=arguments.runs_root,
                run_id=arguments.run_id,
                continue_from_run=arguments.run_root,
                continue_after_stage=arguments.continue_after_stage,
            )
            status = outcome.status
            run_key = None if outcome.run_root is None else _run_key(outcome.run_root)
            run_id = outcome.plan.project_id if outcome.run_root is None else outcome.run_root.name
        elif arguments.operation == "resume":
            if arguments.run_root is None:
                raise ValueError("resume worker 缺少 --run-root")
            resumed = resume_pipeline(arguments.run_root, profile_path=arguments.profile)
            status = resumed.status
            run_key = None
            run_id = arguments.run_root.name
        else:
            if arguments.run_root is None or arguments.decision_record is None:
                raise ValueError("decision worker 缺少 run 或 decision record")
            continued = continue_pipeline_after_decision(
                arguments.run_root,
                decision_record=arguments.decision_record,
                profile_path=arguments.profile,
            )
            status = continued.status
            run_key = None
            run_id = arguments.run_root.name
        status_text = _status_text(status)
        navigation_error = _publish_product_run_navigation(
            record=record,
            run_root=outcome.run_root if arguments.operation == "run" else arguments.run_root,
            runs_root=arguments.runs_root,
            project_id=(
                getattr(outcome.plan, "project_id", None)
                if arguments.operation == "run"
                else record.project_id
            ),
            status=status_text,
        )
        if (
            record.session_id is not None
            and record.stage_number is not None
            and arguments.session_root is not None
            and run_key is not None
        ):
            DesignSessionStore(arguments.session_root).attach_run(
                record.session_id,
                run_key=run_key,
                status=status_text,
                stage_number=record.stage_number,
            )
        if (
            record.self_test_id is not None
            and record.stage_number is not None
            and arguments.self_test_root is not None
            and arguments.self_test_runs_root is not None
        ):
            SelfTestStore(
                arguments.self_test_root,
                arguments.self_test_runs_root,
                profile_path=arguments.profile,
            ).mark_job_finished(
                record.self_test_id,
                stage_number=record.stage_number,
                status=str(getattr(status, "value", status)),
                run_key=run_key,
                run_root=outcome.run_root if arguments.operation == "run" else arguments.run_root,
            )
        updated = record.model_copy(
            update={
                "status": status_text,
                "run_key": run_key,
                "run_id": run_id,
                "updated_at": datetime.now(tz=UTC),
                "error": navigation_error,
            }
        )
        atomic_dump_runtime_model(updated, arguments.job_record)
        return 0
    except Exception as error:
        if (
            record.self_test_id is not None
            and record.stage_number is not None
            and arguments.self_test_root is not None
            and arguments.self_test_runs_root is not None
        ):
            SelfTestStore(
                arguments.self_test_root,
                arguments.self_test_runs_root,
                profile_path=arguments.profile,
            ).mark_job_finished(
                record.self_test_id,
                stage_number=record.stage_number,
                status="operational-failed",
                run_key=None,
                run_root=arguments.run_root,
                error=str(error)[:4096] or error.__class__.__name__,
            )
        failed = record.model_copy(
            update={
                "status": "operational-failed",
                "error": str(error)[:4096] or error.__class__.__name__,
                "updated_at": datetime.now(tz=UTC),
            }
        )
        atomic_dump_runtime_model(failed, arguments.job_record)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
