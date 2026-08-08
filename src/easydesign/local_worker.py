"""Persistent local worker for one canonical EasyDesign step."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import Any

from easydesign.core import (
    ExecutionStatus,
    ManifestStateError,
    RunManifest,
    TargetInputError,
    load_model,
)
from easydesign.orchestration.application import (
    continue_pipeline_after_decision,
    execute_pipeline,
    list_runs,
    resume_pipeline,
)
from easydesign.orchestration.local_jobs import LocalStepJobController
from easydesign.orchestration.local_project import bind_project_run
from easydesign.runtime_guard import (
    LOCAL_WRITE_ROOTS_ENV,
    READ_ONLY_RUNTIME_ENV,
    apply_local_write_sandbox,
)
from easydesign.safe_writes import read_last_text_line
from easydesign.workspace_context import WorkspaceContext


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--job-record", type=Path, required=True)
    return parser


def _manifest_identity(run_root: Path) -> tuple[str, Path]:
    name = read_last_text_line(run_root / "manifests/LATEST")
    path = run_root / "manifests" / name
    run = load_model(path, RunManifest)
    return run.run_id, path


def _failure_status(error: Exception) -> str:
    return "scientific-failed" if isinstance(error, TargetInputError) else "operational-failed"


def _resume_until_boundary(run_root: Path) -> Any:
    """Continue completed internal stages until the run reaches its frozen stop boundary."""

    previous_manifest: Path | None = None
    for _ in range(5):
        outcome = resume_pipeline(run_root)
        _, manifest_path = _manifest_identity(run_root)
        current = load_model(manifest_path, RunManifest)
        if str(getattr(outcome, "status", "")) != "succeeded":
            return outcome
        if current.status is not ExecutionStatus.RUNNING:
            return outcome
        if manifest_path == previous_manifest:
            raise ManifestStateError("resume succeeded 但 run manifest 未前进")
        previous_manifest = manifest_path
    raise ManifestStateError("resume 超过内部 Stage 上限仍未到达冻结边界")


def main() -> int:
    args = _parser().parse_args()
    context = WorkspaceContext.discover(args.job_record)
    controller = LocalStepJobController(context)
    job = controller.load(args.job_record.stem)
    before_run_ids = {item.run_id for item in list_runs(context.runs_root)}
    try:
        if READ_ONLY_RUNTIME_ENV in os.environ:
            declared_roots = os.environ.get(LOCAL_WRITE_ROOTS_ENV, "").split(os.pathsep)
            writable_roots = tuple(Path(value) for value in declared_roots if value)
            expected_roots = (
                context.runtime_root,
                context.projects_root,
                context.runs_root,
                context.archives_root,
            )
            if writable_roots != expected_roots:
                raise OSError("local worker write-root declaration does not match workspace")
            apply_local_write_sandbox(writable_roots)
        outcome: Any
        if job.operation == "run":
            assert job.config_path is not None
            if job.step == 1:
                outcome = execute_pipeline(
                    job.config_path,
                    runs_root=context.runs_root,
                    run_id=job.run_id,
                    source_base_dir=job.project_root,
                )
            else:
                assert job.run_root is not None
                outcome = execute_pipeline(
                    job.config_path,
                    runs_root=context.runs_root,
                    run_id=job.run_id,
                    continue_from_run=job.run_root,
                    continue_after_stage=job.step - 1,
                    source_base_dir=job.project_root,
                )
        elif job.operation == "resume":
            assert job.run_root is not None
            outcome = _resume_until_boundary(job.run_root)
        else:
            assert job.run_root is not None
            assert job.decision_record is not None
            outcome = continue_pipeline_after_decision(
                job.run_root,
                decision_record=job.decision_record,
            )
        run_root = getattr(outcome, "run_root", None) or job.run_root
        run_manifest = getattr(outcome, "run_manifest", None)
        run_id = job.run_id
        if run_root is not None:
            run_id, current_manifest = _manifest_identity(run_root)
            run_manifest = run_manifest or current_manifest
            bind_project_run(job.project_root, run_root)
        controller.update(
            job,
            status=str(getattr(outcome, "status", "succeeded")),
            run_id=run_id,
            run_root=run_root,
            run_manifest=run_manifest,
        )
        return 0
    except Exception as error:
        summaries = list_runs(context.runs_root)
        matching = [
            item
            for item in summaries
            if item.project_id == job.project_id
            and (
                (job.run_id is not None and item.run_id == job.run_id)
                or (job.run_id is None and item.run_id not in before_run_ids)
            )
        ]
        failed_run = max(matching, key=lambda item: item.run_id) if matching else None
        controller.update(
            job,
            status=_failure_status(error),
            run_id=job.run_id if failed_run is None else failed_run.run_id,
            run_root=job.run_root if failed_run is None else failed_run.path,
            run_manifest=(job.run_manifest if failed_run is None else failed_run.latest_manifest),
            error=f"{type(error).__name__}: {str(error)[:4096]}",
        )
        raise


if __name__ == "__main__":
    raise SystemExit(main())
