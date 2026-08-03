"""UI 长任务的持久 launcher；worker 仍调用统一 application API。"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from threading import Thread
from typing import Literal
from uuid import uuid4

import yaml  # type: ignore[import-untyped]

from easydesign.core import ConfigurationError, RunManifest, dump_model, load_model
from easydesign.orchestration import (
    diagnose_runtime,
    next_stage_number,
    validate_run_configuration,
)
from easydesign.orchestration.task_tracking import (
    atomic_dump_runtime_model,
    load_latest_runtime_model,
)
from easydesign.safe_writes import read_last_text_line
from easydesign.workspace_context import WorkspaceContext

from .models import UiJobRecord


def _latest_manifest(run_root: Path) -> RunManifest:
    pointer = run_root / "manifests" / "LATEST"
    try:
        name = read_last_text_line(pointer)
    except OSError as error:
        raise ConfigurationError(f"无法读取 source run: {run_root}") from error
    return load_model(run_root / "manifests" / name, RunManifest)


def clone_run_configuration(
    source_run_root: Path,
    destination: Path,
    *,
    project_id: str,
) -> Path:
    """复制已冻结配置和本地输入到新项目；不修改 source run。"""

    source = source_run_root.expanduser().resolve()
    context = WorkspaceContext.discover()
    target = context.require_write_path(
        destination,
        purpose="UI 项目配置克隆",
    )
    if target.exists() and any(target.iterdir()):
        raise ConfigurationError(f"目标项目目录非空，拒绝覆盖: {target}")
    manifest = _latest_manifest(source)
    config_path = manifest.config_snapshot.verify(source)
    try:
        payload = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as error:
        raise ConfigurationError("source run 配置无法读取") from error
    if not isinstance(payload, dict):
        raise ConfigurationError("source run 配置根节点必须是 object")
    payload["project_id"] = project_id
    stage01 = payload.get("stage01")
    if isinstance(stage01, dict):
        target_block = stage01.get("target")
        source_block = target_block.get("source") if isinstance(target_block, dict) else None
        if isinstance(source_block, dict) and source_block.get("type") == "local-file":
            source_value = source_block.get("path")
            if not isinstance(source_value, str):
                raise ConfigurationError("local-file source 缺少 path")
            original = Path(source_value).expanduser()
            if not original.is_file():
                fallback = source / "input-snapshot" / original.name
                original = fallback if fallback.is_file() else original
            if not original.is_file():
                raise ConfigurationError(
                    "真实重跑需要可读取的原始输入；当前 source run 未保留可复制文件"
                )
            inputs = target / "inputs"
            inputs.mkdir(parents=True, exist_ok=True)
            copied = inputs / original.name
            shutil.copy2(original, copied)
            source_block["path"] = f"inputs/{copied.name}"
    target.mkdir(parents=True, exist_ok=True)
    output = target / "easydesign.yaml"
    output.write_text(
        yaml.safe_dump(payload, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    (target / ".gitignore").write_text("runs/\n", encoding="utf-8")
    return output


class UiJobController:
    """将同步 pipeline 放入独立进程，并以原子 job record 留下操作证据。"""

    def __init__(self, state_root: Path | None = None) -> None:
        selected = WorkspaceContext.discover().ui_job_root if state_root is None else state_root
        self.state_root = Path(selected).expanduser().resolve()
        self.state_root.mkdir(parents=True, exist_ok=True)

    def _path(self, job_id: str) -> Path:
        return self.state_root / f"{job_id}.json"

    @staticmethod
    def _pid_exists(process_id: int) -> bool:
        try:
            os.kill(process_id, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        if sys.platform.startswith("linux"):
            try:
                process_state = (
                    Path(f"/proc/{process_id}/stat")
                    .read_text(encoding="utf-8")
                    .rpartition(") ")[2]
                    .split(maxsplit=1)[0]
                )
            except (OSError, IndexError):
                process_state = ""
            if process_state == "Z":
                return False
        return True

    def _reconcile(self, record: UiJobRecord) -> UiJobRecord:
        """Close a lost local worker without altering stage or GPU evidence."""

        if (
            record.external_job_id is not None
            or record.status not in {"queued", "running"}
            or record.process_id is None
            or self._pid_exists(record.process_id)
        ):
            return record
        failed = record.model_copy(
            update={
                "status": "operational-failed",
                "error": "local-ui-worker-exited-without-terminal-record",
                "updated_at": datetime.now(tz=UTC),
            }
        )
        atomic_dump_runtime_model(failed, self._path(record.job_id))
        return failed

    def load(self, job_id: str) -> UiJobRecord:
        return self._reconcile(load_latest_runtime_model(self._path(job_id), UiJobRecord))

    def list(self) -> tuple[UiJobRecord, ...]:
        return tuple(
            sorted(
                (
                    self._reconcile(load_latest_runtime_model(path, UiJobRecord))
                    for path in self.state_root.glob("job-*.json")
                ),
                key=lambda item: item.updated_at,
                reverse=True,
            )
        )

    def latest_continuation(
        self,
        *,
        run_key: str,
        project_id: str,
        stage_number: int,
    ) -> UiJobRecord | None:
        """Return the durable job that owns a run continuation.

        Records created before the run binding was added did not persist
        ``accepted_run_key`` for managed submissions.  Those records are only
        considered while they still carry an active status, and are scoped by
        the same project and stage so a historical terminal job cannot attach
        itself to a newer run.
        """

        records = self.list()
        exact = [
            item
            for item in records
            if item.accepted_run_key == run_key
            and item.stage_number == stage_number
        ]
        if exact:
            return max(exact, key=lambda item: item.created_at)
        active_statuses = {
            "queued",
            "waiting-resource",
            "admitting",
            "running",
            "drain-requested",
            "submitted",
        }
        legacy = [
            item
            for item in records
            if item.accepted_run_key is None
            and item.project_id == project_id
            and item.stage_number == stage_number
            and item.status in active_statuses
        ]
        if len(legacy) > 1:
            raise ConfigurationError(
                "同项目和阶段存在多个未绑定的活动任务，拒绝自动选择"
            )
        return legacy[0] if legacy else None

    def bind_continuation(
        self,
        job_id: str,
        *,
        accepted_run_key: str,
        status: str | None = None,
        execution_target: Literal["local-current-host", "managed-ssh"] | None = None,
    ) -> UiJobRecord:
        """Append a corrected controller revision for a persisted UI job."""

        current = self.load(job_id)
        updates: dict[str, object] = {
            "accepted_run_key": accepted_run_key,
            "updated_at": datetime.now(tz=UTC),
        }
        if status is not None:
            updates["status"] = status
        if execution_target is not None:
            updates["execution_target"] = execution_target
        if (
            current.accepted_run_key == accepted_run_key
            and (status is None or current.status == status)
            and (
                execution_target is None
                or current.execution_target == execution_target
            )
        ):
            return current
        updated = current.model_copy(update=updates)
        atomic_dump_runtime_model(updated, self._path(job_id))
        return updated

    def launch(
        self,
        *,
        operation: str,
        config_path: Path | None = None,
        run_root: Path | None = None,
        profile_path: Path | None = None,
        runs_root: Path | None = None,
        run_id: str | None = None,
        continue_after_stage: int | None = None,
        decision_record: Path | None = None,
        project_id: str | None = None,
        accepted_run_key: str | None = None,
        session_id: str | None = None,
        session_root: Path | None = None,
        self_test_id: str | None = None,
        self_test_root: Path | None = None,
        self_test_runs_root: Path | None = None,
        stage_number: int | None = None,
        execution_target: Literal["local-current-host", "managed-ssh"] | None = None,
        maximum_gpus: int | None = None,
        confirmed: bool,
    ) -> UiJobRecord:
        if not confirmed:
            raise ConfigurationError("真实运行必须经过 UI 资源摘要确认")
        if operation not in {"run", "resume", "decision"}:
            raise ConfigurationError("UI job operation 只支持 run/resume/decision")
        if session_id is not None and (session_root is None or stage_number is None):
            raise ConfigurationError("产品会话 job 必须同时提供 session root 和 stage")
        if self_test_id is not None and (
            self_test_root is None or self_test_runs_root is None or stage_number is None
        ):
            raise ConfigurationError(
                "开发者自检 job 必须同时提供 self-test root、runs root 和 stage"
            )
        if execution_target not in {None, "local-current-host"}:
            raise ConfigurationError("本地 UI worker 只接受 local-current-host 执行目标")
        if maximum_gpus is not None and maximum_gpus < 1:
            raise ConfigurationError("maximum_gpus 必须是正整数")
        if operation == "run":
            if config_path is None:
                raise ConfigurationError("run job 必须提供 config_path")
            validate_run_configuration(
                config_path,
                profile_path=profile_path,
                runs_root=runs_root,
            )
            start_stage = (
                1
                if run_root is None
                else (
                    continue_after_stage + 1
                    if continue_after_stage is not None
                    else next_stage_number(run_root)
                )
            )
            diagnostic = diagnose_runtime(
                profile_path=profile_path,
                config_path=config_path,
                runs_root=runs_root,
                start_stage=start_stage,
            )
            if not diagnostic.ok:
                failures = "; ".join(
                    item.message for item in diagnostic.checks if str(item.status) == "failed"
                )
                raise ConfigurationError(f"UI preflight 失败: {failures}")
            selected_run_id = run_id
        elif operation == "resume":
            if run_root is None:
                raise ConfigurationError("resume job 必须提供 run_root")
            selected_run_id = _latest_manifest(run_root).run_id
        else:
            if run_root is None or decision_record is None:
                raise ConfigurationError("decision job 必须提供 run_root 和 decision_record")
            selected_run_id = _latest_manifest(run_root).run_id
        now = datetime.now(tz=UTC)
        job_id = f"job-{uuid4().hex[:16]}"
        drain_path = self.state_root / f"{job_id}.drain"
        record = UiJobRecord(
            job_id=job_id,
            operation=operation,
            status="queued",
            config_path=None if config_path is None else str(config_path.resolve()),
            project_id=project_id,
            accepted_run_key=accepted_run_key,
            run_id=selected_run_id,
            session_id=session_id,
            self_test_id=self_test_id,
            stage_number=stage_number,
            execution_target=execution_target,
            maximum_gpus=maximum_gpus,
            created_at=now,
            updated_at=now,
        )
        record_path = self._path(job_id)
        dump_model(record, record_path)
        command = [
            sys.executable,
            "-m",
            "easydesign.ui.worker",
            "--job-record",
            str(record_path),
            "--operation",
            operation,
            "--drain-file",
            str(drain_path),
        ]
        if config_path is not None:
            command.extend(["--config", str(config_path.resolve())])
        if run_root is not None:
            command.extend(["--run-root", str(run_root.resolve())])
        if decision_record is not None:
            command.extend(["--decision-record", str(decision_record.resolve())])
        if profile_path is not None:
            command.extend(["--profile", str(profile_path.resolve())])
        if runs_root is not None:
            command.extend(["--runs-root", str(runs_root.resolve())])
        if run_id is not None:
            command.extend(["--run-id", run_id])
        if continue_after_stage is not None:
            command.extend(["--continue-after-stage", str(continue_after_stage)])
        if session_root is not None:
            command.extend(["--session-root", str(session_root.resolve())])
        if self_test_root is not None:
            command.extend(["--self-test-root", str(self_test_root.resolve())])
        if self_test_runs_root is not None:
            command.extend(["--self-test-runs-root", str(self_test_runs_root.resolve())])
        environment = os.environ.copy()
        environment["EASYDESIGN_UI_DRAIN_FILE"] = str(drain_path)
        if maximum_gpus is not None:
            environment["EASYDESIGN_LOCAL_MAXIMUM_GPUS"] = str(maximum_gpus)
        process = subprocess.Popen(
            command,
            env=environment,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=(os.name != "nt"),
        )
        Thread(
            target=process.wait,
            name=f"easydesign-ui-worker-reaper-{process.pid}",
            daemon=True,
        ).start()
        running = record.model_copy(
            update={
                "status": "running",
                "process_id": process.pid,
                "updated_at": datetime.now(tz=UTC),
            }
        )
        atomic_dump_runtime_model(running, record_path)
        return running

    def accept_external(
        self,
        *,
        operation: str,
        project_id: str,
        stage_number: int,
        external_job_id: str,
        run_id: str,
        session_id: str | None = None,
        status: str = "queued",
        accepted_run_key: str | None = None,
        execution_target: Literal["local-current-host", "managed-ssh"] | None = None,
    ) -> UiJobRecord:
        """Persist a successful remote submission before returning it to the UI.

        The remote executor owns process execution, but the local product still
        needs durable acceptance evidence so that the same stage-freeze contract
        applies to local and SSH execution.
        """

        if stage_number < 1 or stage_number > 7:
            raise ConfigurationError("外部任务阶段必须位于 1–7")
        if not external_job_id.strip():
            raise ConfigurationError("外部任务必须提供稳定 job ID")
        now = datetime.now(tz=UTC)
        record = UiJobRecord(
            job_id=f"job-external-{uuid4().hex[:16]}",
            operation=operation,
            status=status,
            project_id=project_id,
            accepted_run_key=accepted_run_key,
            run_id=run_id,
            external_job_id=external_job_id,
            session_id=session_id,
            stage_number=stage_number,
            execution_target=execution_target,
            created_at=now,
            updated_at=now,
        )
        dump_model(record, self._path(record.job_id))
        return record

    def request_drain(self, job_id: str) -> UiJobRecord:
        current = self.load(job_id)
        if current.status not in {"queued", "running"}:
            raise ConfigurationError("只有 queued/running job 可以请求停止调度")
        drain = self.state_root / f"{job_id}.drain"
        drain.touch(exist_ok=True)
        updated = current.model_copy(
            update={
                "drain_requested": True,
                "updated_at": datetime.now(tz=UTC),
            }
        )
        atomic_dump_runtime_model(updated, self._path(job_id))
        return updated


def launch_pipeline_job(
    controller: UiJobController,
    *,
    config_path: Path,
    profile_path: Path | None = None,
    runs_root: Path | None = None,
    run_id: str | None = None,
    confirmed: bool,
) -> UiJobRecord:
    return controller.launch(
        operation="run",
        config_path=config_path,
        profile_path=profile_path,
        runs_root=runs_root,
        run_id=run_id,
        confirmed=confirmed,
    )


def resume_pipeline_job(
    controller: UiJobController,
    *,
    run_root: Path,
    profile_path: Path | None = None,
    confirmed: bool,
) -> UiJobRecord:
    return controller.launch(
        operation="resume",
        run_root=run_root,
        profile_path=profile_path,
        confirmed=confirmed,
    )


def request_pipeline_drain(
    controller: UiJobController,
    *,
    job_id: str,
) -> UiJobRecord:
    return controller.request_drain(job_id)
