"""Internal detached worker for repository-local backend installation."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
from pathlib import Path

from easydesign.core import dump_model, load_model
from easydesign.orchestration.afo_releases import install_stable_afo_if_available
from easydesign.orchestration.runtime_setup import setup_workspace
from easydesign.orchestration.setup_jobs import (
    SetupJobRequest,
    SetupJobResult,
    SetupProgressRecorder,
)
from easydesign.workspace_context import WorkspaceContext


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="EasyDesign internal setup worker")
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--worker-token", required=True)
    return parser


def main() -> int:
    arguments = _parser().parse_args()
    context = WorkspaceContext.from_root(arguments.workspace)
    request_path = arguments.request.resolve(strict=True)
    context.assert_write_path(request_path)
    request = load_model(request_path, SetupJobRequest)
    job_directory = request_path.parent
    if request.worker_token != arguments.worker_token:
        raise RuntimeError("Setup worker identity 校验失败")
    progress = SetupProgressRecorder(context, request)
    try:
        if request.component is None:
            raise RuntimeError(
                "历史 setup request 没有本地科学组件；只能读取，不能重新启动"
            )
        summary = setup_workspace(
            context,
            component=request.component,
            accepted_license_ids=set(request.accepted_license_ids),
            conda_executable=request.conda_executable,
            pip_index_url=request.pip_index_url,
            source_policy=request.source_policy,
            progress_callback=progress,
        )
        afo = (
            install_stable_afo_if_available(
                source_policy=request.source_policy,
                context=context,
            )
            if summary.ok and request.component == "all"
            else None
        )
        return_code = 0 if summary.ok else 3
        result = SetupJobResult(
            job_id=request.job_id,
            status="succeeded" if summary.ok else "incomplete",
            return_code=return_code,
            completed_at=datetime.now(tz=UTC),
            summary=summary,
            afo=afo,
        )
    except Exception as error:
        return_code = 4
        progress.fail(f"{type(error).__name__}: {error}")
        result = SetupJobResult(
            job_id=request.job_id,
            status="failed",
            return_code=return_code,
            completed_at=datetime.now(tz=UTC),
            error=f"{type(error).__name__}: {error}",
        )
    dump_model(result, job_directory / "result.json")
    return return_code


if __name__ == "__main__":
    raise SystemExit(main())
