"""Persistent local step worker receipts, observation, drain, and resume."""

from __future__ import annotations

import os
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from easydesign.core import ConfigurationError
from easydesign.workspace_context import WorkspaceContext

from .task_tracking import atomic_dump_runtime_model, load_latest_runtime_model

ACTIVE_JOB_STATUSES = {"queued", "running", "drain-requested"}


class LocalStepJob(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: str = "0.1"
    job_id: str
    operation: Literal["run", "resume", "decision"]
    status: str
    project_id: str
    project_root: Path
    step: int = Field(ge=1, le=7)
    config_path: Path | None = None
    decision_record: Path | None = None
    run_id: str | None = None
    run_root: Path | None = None
    run_manifest: Path | None = None
    process_id: int | None = None
    branch: str
    log_path: Path
    drain_path: Path
    created_at: datetime
    updated_at: datetime
    error: str | None = None


def _branch(context: WorkspaceContext) -> str:
    completed = subprocess.run(
        ["git", "branch", "--show-current"],
        cwd=context.root,
        check=False,
        capture_output=True,
        text=True,
    )
    value = completed.stdout.strip()
    return value or "detached"


class LocalStepJobController:
    def __init__(self, context: WorkspaceContext | None = None) -> None:
        self.context = WorkspaceContext.discover() if context is None else context
        self.root = self.context.runtime_root / "state/local-jobs"
        self.root.mkdir(parents=True, exist_ok=True)

    def path(self, job_id: str) -> Path:
        return self.root / f"{job_id}.json"

    @staticmethod
    def _pid_exists(pid: int) -> bool:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        if sys.platform.startswith("linux"):
            try:
                state = (
                    Path(f"/proc/{pid}/stat")
                    .read_text(encoding="utf-8")
                    .rpartition(") ")[2]
                    .split(maxsplit=1)[0]
                )
            except (OSError, IndexError):
                state = ""
            if state == "Z":
                return False
        return True

    def update(self, job: LocalStepJob, **values: object) -> LocalStepJob:
        updated = job.model_copy(
            update={"updated_at": datetime.now(UTC), **values}
        )
        atomic_dump_runtime_model(updated, self.path(job.job_id))
        return updated

    def load(self, job_id: str) -> LocalStepJob:
        job = load_latest_runtime_model(self.path(job_id), LocalStepJob)
        if (
            job.status in ACTIVE_JOB_STATUSES
            and job.process_id is not None
            and not self._pid_exists(job.process_id)
        ):
            return self.update(
                job,
                status="operational-failed",
                error="local-worker-exited-without-terminal-receipt",
            )
        return job

    def list(self, *, project_id: str | None = None) -> tuple[LocalStepJob, ...]:
        values = [
            self.load(path.stem)
            for path in sorted(self.root.glob("job-*.json"))
            if not path.name.endswith(".revisions")
        ]
        if project_id is not None:
            values = [item for item in values if item.project_id == project_id]
        return tuple(sorted(values, key=lambda item: item.created_at, reverse=True))

    def latest(self, project_id: str) -> LocalStepJob | None:
        values = self.list(project_id=project_id)
        return values[0] if values else None

    def launch(
        self,
        *,
        operation: Literal["run", "resume", "decision"],
        project_id: str,
        project_root: Path,
        step: int,
        config_path: Path | None = None,
        decision_record: Path | None = None,
        run_id: str | None = None,
        run_root: Path | None = None,
    ) -> LocalStepJob:
        if operation == "run" and config_path is None:
            raise ConfigurationError("run worker 必须提供 canonical config revision")
        if operation == "resume" and run_root is None:
            raise ConfigurationError("resume worker 必须提供 run_root")
        if operation == "decision" and (run_root is None or decision_record is None):
            raise ConfigurationError("decision worker 必须提供 run_root 和 decision_record")
        previous = self.latest(project_id)
        if previous is not None and previous.status in ACTIVE_JOB_STATUSES:
            raise ConfigurationError(
                f"项目已有活动任务: {previous.job_id} ({previous.status})"
            )
        now = datetime.now(UTC)
        job_id = f"job-{uuid4().hex[:16]}"
        log_path = self.context.runtime_root / "logs/local-jobs" / f"{job_id}.log"
        drain_path = self.root / f"{job_id}.drain"
        record = LocalStepJob(
            job_id=job_id,
            operation=operation,
            status="queued",
            project_id=project_id,
            project_root=project_root.resolve(),
            step=step,
            config_path=None if config_path is None else config_path.resolve(),
            decision_record=(
                None if decision_record is None else decision_record.resolve()
            ),
            run_id=run_id,
            run_root=None if run_root is None else run_root.resolve(),
            branch=_branch(self.context),
            log_path=log_path,
            drain_path=drain_path,
            created_at=now,
            updated_at=now,
        )
        atomic_dump_runtime_model(record, self.path(job_id))
        log_path.parent.mkdir(parents=True, exist_ok=True)
        command = [
            sys.executable,
            "-m",
            "easydesign.local_worker",
            "--job-record",
            str(self.path(job_id)),
        ]
        environment = os.environ.copy()
        environment.update(self.context.child_environment())
        environment.update(
            {
                "EASYDESIGN_LOCAL_DRAIN_FILE": str(drain_path),
                "PYTHONDONTWRITEBYTECODE": "1",
                "HF_HUB_OFFLINE": "1",
                "TRANSFORMERS_OFFLINE": "1",
            }
        )
        with log_path.open("xb") as log:
            process = subprocess.Popen(
                command,
                cwd=self.context.root,
                env=environment,
                stdin=subprocess.DEVNULL,
                stdout=log,
                stderr=subprocess.STDOUT,
                start_new_session=(os.name != "nt"),
            )
        return self.update(record, status="running", process_id=process.pid)

    def request_drain(self, job_id: str) -> LocalStepJob:
        job = self.load(job_id)
        if job.status not in {"queued", "running"}:
            raise ConfigurationError("只有 queued/running job 可以请求 drain")
        if job.step not in {4, 6}:
            raise ConfigurationError("只有 Stage 04/06 的分片调度支持安全 drain")
        job.drain_path.touch(exist_ok=True)
        return self.update(job, status="drain-requested")

    def wait(
        self,
        job_id: str,
        *,
        poll_seconds: float = 1.0,
    ) -> LocalStepJob:
        while True:
            job = self.load(job_id)
            if job.status not in ACTIVE_JOB_STATUSES:
                return job
            time.sleep(poll_seconds)


__all__ = [
    "ACTIVE_JOB_STATUSES",
    "LocalStepJob",
    "LocalStepJobController",
]
