"""UI 长任务的持久 launcher；worker 仍调用统一 application API。"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import yaml  # type: ignore[import-untyped]
from platformdirs import user_data_path

from easydesign.core import ConfigurationError, RunManifest, dump_model, load_model
from easydesign.orchestration import (
    diagnose_runtime,
    next_stage_number,
    validate_run_configuration,
)
from easydesign.orchestration.task_tracking import atomic_dump_runtime_model

from .models import UiJobRecord


def _latest_manifest(run_root: Path) -> RunManifest:
    pointer = run_root / "manifests" / "LATEST"
    try:
        name = pointer.read_text(encoding="utf-8").strip()
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
    target = destination.expanduser().resolve()
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
        selected = (
            user_data_path("easydesign") / "ui" / "jobs"
            if state_root is None
            else state_root
        )
        self.state_root = Path(selected).expanduser().resolve()
        self.state_root.mkdir(parents=True, exist_ok=True)

    def _path(self, job_id: str) -> Path:
        return self.state_root / f"{job_id}.json"

    def load(self, job_id: str) -> UiJobRecord:
        return load_model(self._path(job_id), UiJobRecord)

    def list(self) -> tuple[UiJobRecord, ...]:
        return tuple(
            sorted(
                (load_model(path, UiJobRecord) for path in self.state_root.glob("job-*.json")),
                key=lambda item: item.updated_at,
                reverse=True,
            )
        )

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
        session_id: str | None = None,
        session_root: Path | None = None,
        stage_number: int | None = None,
        confirmed: bool,
    ) -> UiJobRecord:
        if not confirmed:
            raise ConfigurationError("真实运行必须经过 UI 资源摘要确认")
        if operation not in {"run", "resume", "decision"}:
            raise ConfigurationError("UI job operation 只支持 run/resume/decision")
        if session_id is not None and (session_root is None or stage_number is None):
            raise ConfigurationError("产品会话 job 必须同时提供 session root 和 stage")
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
            run_id=selected_run_id,
            session_id=session_id,
            stage_number=stage_number,
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
        environment = os.environ.copy()
        environment["EASYDESIGN_UI_DRAIN_FILE"] = str(drain_path)
        process = subprocess.Popen(
            command,
            env=environment,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=(os.name != "nt"),
        )
        running = record.model_copy(
            update={
                "status": "running",
                "process_id": process.pid,
                "updated_at": datetime.now(tz=UTC),
            }
        )
        atomic_dump_runtime_model(running, record_path)
        return running

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
