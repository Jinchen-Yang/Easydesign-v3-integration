"""FastAPI localhost gateway；浏览器不直接接触机器路径或科学实现。"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import mimetypes
import os
import subprocess
import threading
import webbrowser
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any, cast
from uuid import uuid4

import uvicorn
import yaml  # type: ignore[import-untyped]
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi import Path as ApiPath
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field

import easydesign
from easydesign.core import (
    ArtifactRef,
    ConfigurationError,
    EasyDesignError,
    PathPolicyError,
    canonical_model_sha256,
)
from easydesign.core.hashing import sha256_bytes
from easydesign.orchestration import (
    approve_hotspots,
    archive_project,
    diagnose_runtime,
    export_hotspot_review,
    initialize_project,
    list_project_catalog,
    list_remote_executor_ids,
    list_remote_job_records,
    list_runs,
    materialize_continuation_config,
    observe_remote_pipeline,
    probe_remote_executor,
    read_pipeline_progress,
    restore_project,
    resume_remote_pipeline,
    stage_form_definition,
    submit_remote_pipeline,
    sync_remote_pipeline,
    validate_run_configuration,
)
from easydesign.orchestration.decisions import approve_decision, show_decision
from easydesign.orchestration.runtime_setup import (
    SETUP_COMPONENT_IDS,
    asset_status,
    environment_status,
    initialize_workspace_metadata,
    setup_plan,
)
from easydesign.safe_writes import quarantine_if_workspace_path, read_last_text_line
from easydesign.stages.s02_hotspot_discovery import RegionMethod
from easydesign.workspace_context import WorkspaceContext

from .execution import get_execution_progress
from .jobs import UiJobController, clone_run_configuration
from .models import DesignSession, SelfTestRecord, UiJobRecord
from .projections import (
    create_demo_replay,
    create_draft_order_package,
    get_project_projection,
    get_run_projection,
    get_stage_projection,
    stream_run_events,
)
from .regions import get_region_editor_projection
from .security import ArtifactTokenSigner, UiRunRegistry
from .selftest import SelfTestStore
from .sessions import DesignSessionStore
from .stage05 import (
    get_filter_candidate,
    get_filter_overview,
    list_filter_candidates,
    list_filter_strategies,
    metric_catalog,
)

LOCAL_HOST = "127.0.0.1"
MAX_UPLOAD_BYTES = 64 * 1024 * 1024


class UploadRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    filename: str = Field(min_length=1, max_length=255)
    content_base64: str


class UploadReceipt(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    upload_token: str
    filename: str
    size_bytes: int
    sha256: str


class ProjectCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: str
    target_id: str | None = None
    source_type: str
    source_value: str
    taxon_id: int | None = None
    chain: str | None = None
    execution_mode: str = "review-gated"
    design_intent: str = "exploratory"
    stop_after_stage: int = Field(default=1, ge=1, le=7)
    stage02_method: str | None = None
    source_run_key: str | None = None
    design_mode: str = "full-workflow"
    session_id: str | None = None


class DesignSessionCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: str
    design_mode: str
    execution_mode: str = "review-gated"


class ContinuationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str
    stage_number: int = Field(ge=2, le=7)
    execution_mode: str = "review-gated"
    options: dict[str, Any] = Field(default_factory=dict)
    run_id: str | None = None
    confirmed: bool = False


class CatalogActionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    confirmed: bool = False


class RegionRevisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str
    execution_mode: str = "review-gated"
    regions: list[dict[str, Any]] = Field(min_length=1, max_length=3)
    approved_by: str = Field(min_length=1, max_length=256)
    acknowledge_user_provided_regions: bool = False
    acknowledge_evidence_limitations: bool = False
    run_id: str | None = None
    confirmed: bool = False


class SelfTestRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: str
    confirmed: bool = False


class SelfTestStageRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stage_number: int = Field(ge=1, le=7)
    confirmed: bool = False


class SetupLaunchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    minimal: bool = False
    component: str | None = None
    accepted_license_ids: list[str] = Field(default_factory=list)
    confirmed: bool = False


class ConfigUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    yaml_text: str = Field(min_length=1, max_length=1_000_000)


class PreflightRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: str
    executor_id: str | None = None


class LaunchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: str
    run_id: str | None = None
    executor_id: str | None = None
    session_id: str | None = None
    stage_number: int | None = Field(default=None, ge=1, le=7)
    confirmed: bool = False


class CloneRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: str


class ConfirmedActionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    confirmed: bool = False


class RemoteSyncRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: str = Field(default="metadata", pattern=r"^(metadata|complete)$")
    confirmed: bool = False


class DecisionApprovalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    selected_option_ids: list[str] = Field(min_length=1)
    approved_by: str = Field(min_length=1, max_length=256)
    acknowledgement: str | None = Field(default=None, max_length=4096)
    confirmed: bool = False


class HotspotApprovalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    yaml_text: str = Field(min_length=1, max_length=1_000_000)
    confirmed: bool = False


class UiServiceState:
    def __init__(
        self,
        *,
        runs_root: Path,
        projects_root: Path,
        profile_path: Path | None,
        job_root: Path | None,
    ) -> None:
        self.workspace = WorkspaceContext.discover(runs_root)
        initialize_workspace_metadata(self.workspace)
        self.registry = UiRunRegistry(
            self.workspace.require_write_path(runs_root, purpose="UI runs root")
        )
        self.signer = ArtifactTokenSigner()
        self.projects_root = self.workspace.require_write_path(
            projects_root,
            purpose="UI projects root",
        )
        self.projects_root.mkdir(parents=True, exist_ok=True)
        selected_profile = self.workspace.profile_path if profile_path is None else profile_path
        self.profile_path = self.workspace.require_write_path(
            selected_profile,
            purpose="UI runtime profile",
        )
        selected_jobs = self.workspace.ui_job_root if job_root is None else job_root
        self.jobs = UiJobController(
            self.workspace.require_write_path(selected_jobs, purpose="UI job root")
        )
        self.ui_state_root = self.workspace.runtime_root / "state" / "ui"
        self.ui_state_root.mkdir(parents=True, exist_ok=True)
        self.sessions = DesignSessionStore(self.ui_state_root / "design-sessions")
        self.self_tests = SelfTestStore(
            self.ui_state_root / "self-tests",
            self.registry.runs_root,
            workspace=self.workspace,
            profile_path=self.profile_path,
        )
        self.upload_root = self.workspace.runtime_root / "tmp" / "ui-uploads"
        self.upload_root.mkdir(parents=True, exist_ok=True)
        self.temporary_root = self.workspace.runtime_root / "tmp" / "ui"
        self.temporary_root.mkdir(parents=True, exist_ok=True)
        self.uploads: dict[str, Path] = {}
        self.setup_job_root = self.workspace.runtime_root / "state" / "setup-jobs"
        self.setup_job_root.mkdir(parents=True, exist_ok=True)
        self.setup_processes: dict[str, subprocess.Popen[bytes]] = {}

    def project_config(self, project_id: str) -> Path:
        root = (self.projects_root / project_id).resolve()
        try:
            root.relative_to(self.projects_root)
        except ValueError as error:
            raise PathPolicyError("Project ID 逃出 UI projects root") from error
        pointer = root / "CONFIG_CURRENT"
        path = root / "easydesign.yaml"
        if pointer.is_file():
            selected = Path(read_last_text_line(pointer))
            if selected.is_absolute():
                raise PathPolicyError("CONFIG_CURRENT 必须保存项目内相对路径")
            path = (root / selected).resolve()
            try:
                path.relative_to(root)
            except ValueError as error:
                raise PathPolicyError("CONFIG_CURRENT 逃出项目目录") from error
        if not path.is_file():
            raise ConfigurationError(f"项目配置不存在: {project_id}")
        return path

    def publish_project_config(self, project_id: str, yaml_text: str) -> Path:
        root = (self.projects_root / project_id).resolve()
        try:
            root.relative_to(self.projects_root)
        except ValueError as error:
            raise PathPolicyError("Project ID 逃出 UI projects root") from error
        revisions = root / "config-revisions"
        revisions.mkdir(parents=True, exist_ok=True)
        existing = sorted(revisions.glob("easydesign.rev-*.yaml"))
        revision = len(existing) + 1
        destination = revisions / f"easydesign.rev-{revision:06d}.yaml"
        with destination.open("x", encoding="utf-8") as handle:
            handle.write(yaml_text)
            if not yaml_text.endswith("\n"):
                handle.write("\n")
        self.activate_project_config(project_id, destination)
        return destination

    def activate_project_config(self, project_id: str, config_path: Path) -> None:
        root = (self.projects_root / project_id).resolve()
        selected = config_path.resolve()
        try:
            relative = selected.relative_to(root)
        except ValueError as error:
            raise PathPolicyError("项目配置必须位于对应项目目录内") from error
        if not selected.is_file():
            raise ConfigurationError("准备激活的项目配置不存在")
        with (root / "CONFIG_CURRENT").open("a", encoding="utf-8") as handle:
            handle.write(f"{relative.as_posix()}\n")

    def temporary_file(self, *, prefix: str, suffix: str) -> Path:
        return self.temporary_root / f"{prefix}-{uuid4().hex}{suffix}"

    def projects(self) -> tuple[str, ...]:
        values: list[str] = []
        for root in self.projects_root.iterdir():
            if not root.is_dir():
                continue
            if (root / "easydesign.yaml").is_file() or (root / "CONFIG_CURRENT").is_file():
                values.append(root.name)
        return tuple(sorted(values))

    def discover_runs(self) -> None:
        for summary in list_runs(self.registry.runs_root):
            if summary.integrity_status == "verified":
                self.registry.register(summary.path)

    def launch_setup(
        self,
        *,
        minimal: bool,
        component: str | None,
        accepted_license_ids: tuple[str, ...],
    ) -> dict[str, Any]:
        job_id = f"setup-{datetime.now(tz=UTC).strftime('%Y%m%dT%H%M%SZ')}-{uuid4().hex[:10]}"
        job_root = self.setup_job_root / job_id
        job_root.mkdir()
        command = [str(self.workspace.root / "easydesign"), "setup"]
        if minimal:
            command.append("--minimal")
        if component is not None:
            command.extend(("--component", component))
        for asset_id in accepted_license_ids:
            command.extend(("--accept-license", asset_id))
        stdout_path = self.workspace.runtime_root / "logs" / f"{job_id}.stdout.log"
        stderr_path = self.workspace.runtime_root / "logs" / f"{job_id}.stderr.log"
        stdout_path.parent.mkdir(parents=True, exist_ok=True)
        with (
            stdout_path.open("xb") as stdout,
            stderr_path.open("xb") as stderr,
        ):
            process = subprocess.Popen(
                command,
                cwd=self.workspace.root,
                env={**os.environ, **self.workspace.child_environment()},
                stdin=subprocess.DEVNULL,
                stdout=stdout,
                stderr=stderr,
                shell=False,
                start_new_session=True,
            )
        request_path = job_root / "request.json"
        with request_path.open("x", encoding="utf-8") as handle:
            json.dump(
                {
                    "schema_version": "0.1",
                    "job_id": job_id,
                    "command": command,
                    "minimal": minimal,
                    "component": component,
                    "accepted_license_ids": list(accepted_license_ids),
                    "pid": process.pid,
                    "started_at": datetime.now(tz=UTC).isoformat(),
                    "stdout": stdout_path.relative_to(self.workspace.root).as_posix(),
                    "stderr": stderr_path.relative_to(self.workspace.root).as_posix(),
                },
                handle,
                ensure_ascii=False,
                indent=2,
            )
            handle.write("\n")
        self.setup_processes[job_id] = process
        return {"job_id": job_id, "status": "running", "pid": process.pid}

    def setup_jobs(self) -> list[dict[str, Any]]:
        jobs: list[dict[str, Any]] = []
        for request_path in sorted(self.setup_job_root.glob("*/request.json"), reverse=True):
            payload = json.loads(request_path.read_text(encoding="utf-8"))
            job_id = str(payload["job_id"])
            process = self.setup_processes.get(job_id)
            if process is not None:
                return_code = process.poll()
                status = (
                    "running"
                    if return_code is None
                    else ("succeeded" if return_code == 0 else "incomplete")
                )
            else:
                return_code = None
                try:
                    os.kill(int(payload["pid"]), 0)
                except (OSError, ValueError):
                    status = "finished-before-ui-restart"
                else:
                    status = "running"
            jobs.append({**payload, "status": status, "return_code": return_code})
        return jobs


def _state(request: Request) -> UiServiceState:
    return cast(UiServiceState, request.app.state.easydesign)


def _project_to_dict(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    return value


def _safe_filename(value: str) -> str:
    selected = Path(value).name
    if selected in {"", ".", ".."} or selected != value:
        raise ConfigurationError("上传文件名必须是不含路径的 basename")
    return selected


def _raise_http(error: Exception) -> None:
    if isinstance(error, PathPolicyError):
        raise HTTPException(status_code=403, detail=str(error)) from error
    if isinstance(error, (ConfigurationError, EasyDesignError, ValueError)):
        raise HTTPException(status_code=400, detail=str(error)) from error
    raise error


def create_ui_app(
    *,
    runs_root: Path,
    projects_root: Path | None = None,
    profile_path: Path | None = None,
    job_root: Path | None = None,
) -> FastAPI:
    """创建只在调用者显式启动时运行的本地 UI application。"""

    selected_projects = (
        runs_root.expanduser().resolve().parent / "projects"
        if projects_root is None
        else projects_root
    )
    state = UiServiceState(
        runs_root=runs_root,
        projects_root=selected_projects,
        profile_path=profile_path,
        job_root=job_root,
    )
    state.discover_runs()
    app = FastAPI(
        title="EasyDesign Scientific Workbench",
        version=easydesign.__version__,
        docs_url=None,
        redoc_url=None,
        openapi_url="/api/v1/openapi.json",
    )
    app.state.easydesign = state

    @app.middleware("http")
    async def local_security(request: Request, call_next: Any) -> Any:
        host = request.headers.get("host", "").split(":", maxsplit=1)[0].lower()
        if host not in {"127.0.0.1", "localhost", "testserver"}:
            return JSONResponse(status_code=403, content={"detail": "UI 只接受 localhost 请求"})
        response = await call_next(request)
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self' 'unsafe-eval'; "
            "style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; "
            "font-src 'self' data:; connect-src 'self' data: blob:; "
            "worker-src 'self' blob:; "
            "object-src 'none'; base-uri 'none'; frame-ancestors 'none'"
        )
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.get("/api/v1/health")
    def health() -> dict[str, Any]:
        return {
            "status": "ok",
            "version": easydesign.__version__,
            "host_policy": "localhost-only",
            "science_source": "manifest-only",
        }

    @app.get("/api/v1/install/plan")
    def install_plan(
        request: Request,
        minimal: bool = False,
        component: str | None = None,
    ) -> dict[str, Any]:
        service = _state(request)
        return setup_plan(
            service.workspace,
            minimal=minimal,
            component=component,
        )

    @app.get("/api/v1/install/status")
    def install_status(request: Request) -> dict[str, Any]:
        service = _state(request)
        return {
            "workspace": str(service.workspace.root),
            "plan": setup_plan(service.workspace, minimal=False),
            "component_plans": {
                component: setup_plan(
                    service.workspace,
                    minimal=False,
                    component=component,
                )
                for component in SETUP_COMPONENT_IDS
            },
            "environments": environment_status(service.workspace)["environments"],
            "assets": asset_status(service.workspace)["assets"],
            "jobs": service.setup_jobs(),
            "quarantine": {
                "path": "runtime/quarantine",
                "entries": len(
                    tuple(
                        (
                            service.workspace.runtime_root / "quarantine"
                        ).glob("*")
                    )
                ),
            },
        }

    @app.post("/api/v1/install/setup")
    def launch_install(
        payload: SetupLaunchRequest,
        request: Request,
    ) -> dict[str, Any]:
        service = _state(request)
        if not payload.confirmed:
            raise HTTPException(status_code=400, detail="安装必须明确 confirmed=true")
        if payload.minimal and payload.component is not None:
            raise HTTPException(
                status_code=400,
                detail="minimal 与 component 不能同时指定",
            )
        if (
            payload.component is not None
            and payload.component not in SETUP_COMPONENT_IDS
        ):
            raise HTTPException(status_code=400, detail="未知安装组件")
        return service.launch_setup(
            minimal=payload.minimal,
            component=payload.component,
            accepted_license_ids=tuple(payload.accepted_license_ids),
        )

    @app.get("/api/v1/projects")
    def projects(request: Request) -> dict[str, Any]:
        service = _state(request)
        try:
            service.discover_runs()
            summaries = list_runs(service.registry.runs_root)
            project_ids = sorted({item.project_id for item in summaries})
            return {
                "projects": [
                    _project_to_dict(
                        get_project_projection(
                            project_id,
                            registry=service.registry,
                            signer=service.signer,
                        )
                    )
                    for project_id in project_ids
                ],
                "editable_projects": service.projects(),
            }
        except Exception as error:
            _raise_http(error)
            raise

    @app.get("/api/v1/project-catalog")
    def project_catalog(
        request: Request,
        include_archived: bool = True,
        include_developer_smoke: bool = True,
    ) -> dict[str, Any]:
        service = _state(request)
        try:
            entries = list_project_catalog(
                service.registry.runs_root,
                include_archived=include_archived,
                include_developer_smoke=include_developer_smoke,
            )
            return {
                "entries": [
                    {
                        "project_id": entry.project_id,
                        "category": entry.category,
                        "run_count": entry.run_count,
                        "paths": list(entry.paths),
                    }
                    for entry in entries
                ]
            }
        except Exception as error:
            _raise_http(error)
            raise

    @app.post("/api/v1/project-catalog/{project_id}/archive")
    def archive_catalog_project(
        project_id: str,
        payload: CatalogActionRequest,
        request: Request,
    ) -> dict[str, Any]:
        service = _state(request)
        try:
            if not payload.confirmed:
                raise ConfigurationError("归档项目必须明确 confirmed=true")
            referenced = {
                record.submission.project_id for record in list_remote_job_records()
            }
            if project_id in referenced:
                raise ConfigurationError(
                    "项目仍被控制端远程任务记录引用；请先确认远程任务终态并移除引用"
                )
            outcome = archive_project(service.registry.runs_root, project_id)
            return {
                "project_id": outcome.project_id,
                "category": outcome.category,
                "moved_paths": [list(item) for item in outcome.moved_paths],
            }
        except Exception as error:
            _raise_http(error)
            raise

    @app.post("/api/v1/project-catalog/{project_id}/restore")
    def restore_catalog_project(
        project_id: str,
        payload: CatalogActionRequest,
        request: Request,
    ) -> dict[str, Any]:
        service = _state(request)
        try:
            if not payload.confirmed:
                raise ConfigurationError("恢复项目必须明确 confirmed=true")
            outcome = restore_project(service.registry.runs_root, project_id)
            service.discover_runs()
            return {
                "project_id": outcome.project_id,
                "category": outcome.category,
                "moved_paths": [list(item) for item in outcome.moved_paths],
            }
        except Exception as error:
            _raise_http(error)
            raise

    @app.get("/api/v1/design-sessions")
    def design_sessions(request: Request) -> tuple[DesignSession, ...]:
        return _state(request).sessions.list()

    @app.post("/api/v1/design-sessions")
    def create_design_session(
        payload: DesignSessionCreateRequest,
        request: Request,
    ) -> DesignSession:
        try:
            return _state(request).sessions.create(
                project_id=payload.project_id,
                design_mode=payload.design_mode,
                execution_mode=payload.execution_mode,
            )
        except Exception as error:
            _raise_http(error)
            raise

    @app.get("/api/v1/self-tests")
    def self_tests(request: Request) -> tuple[SelfTestRecord, ...]:
        return _state(request).self_tests.list()

    @app.post("/api/v1/self-tests")
    def run_self_test(
        payload: SelfTestRequest,
        request: Request,
    ) -> SelfTestRecord:
        service = _state(request)
        try:
            if not payload.confirmed:
                raise ConfigurationError("开发者自检必须明确 confirmed=true")
            if payload.mode == "deterministic-seven-stage":
                return service.self_tests.run_deterministic()
            if payload.mode == "real-backend-micro":
                return service.self_tests.prepare_real_backend()
            raise ConfigurationError("未知的开发者自检模式")
        except Exception as error:
            _raise_http(error)
            raise

    @app.post("/api/v1/self-tests/{self_test_id}/stages/{stage_number}/run")
    def run_self_test_stage(
        self_test_id: str,
        stage_number: int,
        payload: SelfTestStageRunRequest,
        request: Request,
    ) -> dict[str, Any]:
        service = _state(request)
        try:
            if not payload.confirmed:
                raise ConfigurationError("真实后端自检必须明确 confirmed=true")
            if payload.stage_number != stage_number:
                raise ConfigurationError("URL stage 与请求 stage_number 不一致")
            record = service.self_tests.load(self_test_id)
            if stage_number in {6, 7}:
                updated = service.self_tests.run_adapter_probe(
                    self_test_id,
                    stage_number=stage_number,
                )
                return {"record": updated.model_dump(mode="json"), "job": None}
            source_run = (
                None
                if record.run_relative_path is None
                else service.self_tests.runs_root / record.run_relative_path
            )
            config_path = service.self_tests.stage_config(
                self_test_id,
                stage_number=stage_number,
                source_run_root=source_run,
            )
            job = service.jobs.launch(
                operation="run",
                config_path=config_path,
                run_root=source_run,
                profile_path=service.profile_path,
                runs_root=service.registry.runs_root,
                run_id=(
                    f"{self_test_id}-stage01"
                    if stage_number == 1
                    else None
                ),
                continue_after_stage=(
                    None if stage_number == 1 else stage_number - 1
                ),
                self_test_id=self_test_id,
                self_test_root=service.self_tests.root,
                self_test_runs_root=service.self_tests.runs_root,
                stage_number=stage_number,
                confirmed=True,
            )
            updated = service.self_tests.mark_job_started(
                self_test_id,
                stage_number=stage_number,
                job_id=job.job_id,
                config_path=config_path,
            )
            return {
                "record": updated.model_dump(mode="json"),
                "job": job.model_dump(mode="json"),
            }
        except Exception as error:
            _raise_http(error)
            raise

    @app.get("/api/v1/design-sessions/{session_id}")
    def design_session(session_id: str, request: Request) -> DesignSession:
        try:
            return _state(request).sessions.load(session_id)
        except Exception as error:
            _raise_http(error)
            raise

    @app.get("/api/v1/config/forms/{stage_number}")
    def config_form(stage_number: int) -> dict[str, Any]:
        try:
            return stage_form_definition(stage_number)
        except Exception as error:
            _raise_http(error)
            raise

    @app.get("/api/v1/projects/{project_id}")
    def project(project_id: str, request: Request) -> Any:
        service = _state(request)
        try:
            service.discover_runs()
            return get_project_projection(
                project_id,
                registry=service.registry,
                signer=service.signer,
            )
        except Exception as error:
            _raise_http(error)
            raise

    @app.post("/api/v1/uploads")
    def upload(payload: UploadRequest, request: Request) -> UploadReceipt:
        service = _state(request)
        filename = _safe_filename(payload.filename)
        try:
            content = base64.b64decode(payload.content_base64, validate=True)
        except ValueError as error:
            raise HTTPException(status_code=400, detail="上传内容不是合法 base64") from error
        if len(content) > MAX_UPLOAD_BYTES:
            raise HTTPException(status_code=413, detail="单文件上限为 64 MiB")
        if not content:
            raise HTTPException(status_code=400, detail="不能上传空文件")
        token = f"upload-{uuid4().hex}"
        upload_directory = service.upload_root / token
        upload_directory.mkdir()
        target = upload_directory / filename
        with target.open("xb") as handle:
            handle.write(content)
        service.uploads[token] = target
        return UploadReceipt(
            upload_token=token,
            filename=filename,
            size_bytes=len(content),
            sha256=sha256_bytes(content),
        )

    @app.post("/api/v1/uploads/raw")
    async def upload_raw(
        request: Request,
        filename: Annotated[str, Query(min_length=1, max_length=255)],
    ) -> UploadReceipt:
        """流式接收浏览器文件，避免先在浏览器生成完整 Base64 副本。"""

        service = _state(request)
        safe_filename = _safe_filename(filename)
        content_length = request.headers.get("content-length")
        if content_length is not None:
            try:
                declared_size = int(content_length)
            except ValueError as error:
                raise HTTPException(status_code=400, detail="Content-Length 非法") from error
            if declared_size > MAX_UPLOAD_BYTES:
                raise HTTPException(status_code=413, detail="单文件上限为 64 MiB")
        token = f"upload-{uuid4().hex}"
        upload_directory = service.upload_root / token
        upload_directory.mkdir()
        target = upload_directory / safe_filename
        size_bytes = 0
        digest = hashlib.sha256()
        try:
            with target.open("xb") as handle:
                async for chunk in request.stream():
                    if not chunk:
                        continue
                    size_bytes += len(chunk)
                    if size_bytes > MAX_UPLOAD_BYTES:
                        raise HTTPException(status_code=413, detail="单文件上限为 64 MiB")
                    handle.write(chunk)
                    digest.update(chunk)
            if size_bytes == 0:
                raise HTTPException(status_code=400, detail="不能上传空文件")
        except BaseException:
            quarantine_if_workspace_path(
                upload_directory,
                operation=token,
                reason="UI 文件接收未完成",
            )
            raise
        service.uploads[token] = target
        return UploadReceipt(
            upload_token=token,
            filename=safe_filename,
            size_bytes=size_bytes,
            sha256=digest.hexdigest(),
        )

    @app.post("/api/v1/projects")
    def initialize(payload: ProjectCreateRequest, request: Request) -> dict[str, Any]:
        service = _state(request)
        try:
            if payload.design_mode == "stepwise" and payload.stop_after_stage != 1:
                raise ConfigurationError("按步骤设计首次运行只能停止在 Stage 01")
            if payload.design_mode == "developer-smoke":
                raise ConfigurationError("开发者自检必须使用专用自检接口")
            session = (
                service.sessions.create(
                    project_id=payload.project_id,
                    design_mode=payload.design_mode,
                    execution_mode=payload.execution_mode,
                )
                if payload.session_id is None
                else service.sessions.load(payload.session_id)
            )
            if session.project_id != payload.project_id:
                raise ConfigurationError("产品会话与项目 ID 不一致")
            source_value = payload.source_value
            kwargs: dict[str, Any] = {
                "project_root": service.projects_root / payload.project_id,
                "project_id": payload.project_id,
                "target_id": payload.target_id,
                "execution_mode": payload.execution_mode,
                "design_intent": payload.design_intent,
                "stop_after_stage": payload.stop_after_stage,
                "stage02_method": payload.stage02_method,
            }
            uploaded_source: Path | None = None
            if payload.source_type == "local-file":
                try:
                    uploaded_source = service.uploads[source_value]
                    kwargs["target"] = uploaded_source
                except KeyError as error:
                    raise ConfigurationError("未知或已失效的 upload token") from error
            elif payload.source_type == "pdb-id":
                kwargs["pdb_id"] = source_value
                kwargs["chain"] = payload.chain
            elif payload.source_type == "uniprot":
                kwargs["uniprot"] = source_value
            elif payload.source_type == "uniprot-search":
                kwargs["uniprot_query"] = source_value
                kwargs["taxon_id"] = payload.taxon_id
            elif payload.source_type == "target-bundle":
                if payload.source_run_key is None:
                    raise ConfigurationError("Target Bundle 入口必须选择 source run")
                claims = service.signer.verify(source_value)
                if claims.run_key != payload.source_run_key:
                    raise ConfigurationError("Target Bundle token 与 source run 不一致")
                source_run_root = service.registry.resolve(payload.source_run_key)
                reference = ArtifactRef(
                    artifact_id="target-bundle",
                    role="target-bundle",
                    relative_path=claims.relative_path,
                    file_format="json",
                    sha256=claims.sha256,
                    size_bytes=claims.size_bytes,
                )
                kwargs["target_bundle"] = reference.verify(source_run_root)
                kwargs["source_run_root"] = source_run_root
            else:
                raise ConfigurationError(f"不支持的 source_type: {payload.source_type}")
            outcome = initialize_project(**kwargs)
            session = service.sessions.add_config_revision(
                session.session_id,
                stage_number=1 if payload.design_mode == "stepwise" else payload.stop_after_stage,
                config_path=outcome.config_path,
            )
            if uploaded_source is not None:
                service.uploads.pop(source_value, None)
                quarantine_if_workspace_path(
                    uploaded_source.parent,
                    operation=f"consumed-{source_value}",
                    reason="上传输入已复制进项目，保留原接收证据",
                )
            return {
                "project_id": payload.project_id,
                "config": outcome.config_path.read_text(encoding="utf-8"),
                "status": "draft",
                "session": session.model_dump(mode="json"),
            }
        except Exception as error:
            _raise_http(error)
            raise

    @app.get("/api/v1/projects/{project_id}/config")
    def read_config(project_id: str, request: Request) -> dict[str, str]:
        try:
            path = _state(request).project_config(project_id)
            return {"project_id": project_id, "yaml": path.read_text(encoding="utf-8")}
        except Exception as error:
            _raise_http(error)
            raise

    @app.put("/api/v1/projects/{project_id}/config")
    def update_config(
        project_id: str,
        payload: ConfigUpdateRequest,
        request: Request,
    ) -> dict[str, Any]:
        service = _state(request)
        try:
            operation_id = f"config-validation-{uuid4().hex}"
            temporary = service.temporary_root / f"{operation_id}.yaml"
            with temporary.open("x", encoding="utf-8") as handle:
                handle.write(payload.yaml_text)
            try:
                plan = validate_run_configuration(
                    temporary,
                    profile_path=service.profile_path,
                )
            finally:
                quarantine_if_workspace_path(
                    temporary,
                    operation=operation_id,
                    reason="UI 配置校验 staging 已终止",
                )
            published = service.publish_project_config(project_id, payload.yaml_text)
            return {
                "status": "valid",
                "config_path": published.relative_to(service.projects_root).as_posix(),
                "plan": plan.model_dump(mode="json"),
            }
        except Exception as error:
            _raise_http(error)
            raise

    @app.post("/api/v1/preflight")
    def preflight(payload: PreflightRequest, request: Request) -> dict[str, Any]:
        service = _state(request)
        try:
            config = service.project_config(payload.project_id)
            plan = validate_run_configuration(config, profile_path=service.profile_path)
            if payload.executor_id is None:
                diagnostic: Any = diagnose_runtime(
                    profile_path=service.profile_path,
                    config_path=config,
                )
            else:
                diagnostic = {
                    "status": "remote-reachable",
                    "executor_id": payload.executor_id,
                    "probe": probe_remote_executor(
                        executor_id=payload.executor_id,
                        profile_path=service.profile_path,
                    ).model_dump(mode="json"),
                    "note": (
                        "远端提交前还会在冻结输入后执行配置校验和按需环境检查。"
                    ),
                }
            return {
                "plan": plan.model_dump(mode="json"),
                "diagnostic": (
                    diagnostic.model_dump(mode="json")
                    if isinstance(diagnostic, BaseModel)
                    else diagnostic
                ),
            }
        except Exception as error:
            _raise_http(error)
            raise

    @app.post("/api/v1/jobs")
    def launch(payload: LaunchRequest, request: Request) -> Any:
        service = _state(request)
        try:
            if (payload.session_id is None) != (payload.stage_number is None):
                raise ConfigurationError(
                    "产品会话启动必须同时提供 session_id 和 stage_number"
                )
            if payload.session_id is not None:
                session = service.sessions.load(payload.session_id)
                if session.project_id != payload.project_id:
                    raise ConfigurationError("产品会话与启动项目不一致")
            if payload.executor_id is not None:
                if not payload.confirmed:
                    raise ConfigurationError("远程真实启动需要 confirmed=true")
                run_id = payload.run_id or f"remote-{uuid4().hex[:16]}"
                submission = submit_remote_pipeline(
                    executor_id=payload.executor_id,
                    job_id=f"ui-{uuid4().hex[:16]}",
                    run_id=run_id,
                    config_path=service.project_config(payload.project_id),
                    project_root=service.project_config(payload.project_id).parent,
                    profile_path=service.profile_path,
                )
                return {
                    "kind": "remote",
                    "executor_id": submission.executor_id,
                    "job_id": submission.job_id,
                    "project_id": submission.project_id,
                    "run_id": submission.run_id,
                    "submitted_at": submission.submitted_at.isoformat(),
                    "status": submission.status,
                }
            return service.jobs.launch(
                operation="run",
                config_path=service.project_config(payload.project_id),
                profile_path=service.profile_path,
                runs_root=service.registry.runs_root,
                run_id=payload.run_id,
                session_id=payload.session_id,
                session_root=(
                    None if payload.session_id is None else service.sessions.root
                ),
                stage_number=payload.stage_number,
                confirmed=payload.confirmed,
            )
        except Exception as error:
            _raise_http(error)
            raise

    @app.get("/api/v1/remote-executors")
    def remote_executors(request: Request) -> dict[str, Any]:
        service = _state(request)
        try:
            return {
                "executors": [
                    {"executor_id": executor_id, "label": executor_id}
                    for executor_id in list_remote_executor_ids(
                        profile_path=service.profile_path
                    )
                ]
            }
        except Exception as error:
            _raise_http(error)
            raise

    @app.get("/api/v1/remote-jobs")
    def remote_jobs() -> dict[str, Any]:
        return {
            "jobs": [
                {
                    "executor_id": record.submission.executor_id,
                    "job_id": record.submission.job_id,
                    "project_id": record.submission.project_id,
                    "run_id": record.submission.run_id,
                    "submitted_at": record.submission.submitted_at.isoformat(),
                    "active_unit_name": record.active_unit_name,
                    "resume_count": record.resume_count,
                }
                for record in list_remote_job_records()
            ]
        }

    @app.get("/api/v1/remote-jobs/{executor_id}/{job_id}")
    def remote_job(executor_id: str, job_id: str, request: Request) -> dict[str, Any]:
        service = _state(request)
        try:
            observation = observe_remote_pipeline(
                executor_id=executor_id,
                job_id=job_id,
                profile_path=service.profile_path,
            )
            return {
                "executor_id": observation.executor_id,
                "job_id": observation.job_id,
                "checked_at": observation.checked_at.isoformat(),
                "worker": observation.worker.model_dump(mode="json"),
                "progress": (
                    None
                    if observation.progress is None
                    else observation.progress.model_dump(mode="json")
                ),
                "progress_error": observation.progress_error,
            }
        except Exception as error:
            _raise_http(error)
            raise

    @app.post("/api/v1/remote-jobs/{executor_id}/{job_id}/resume")
    def remote_resume(
        executor_id: str,
        job_id: str,
        payload: ConfirmedActionRequest,
        request: Request,
    ) -> dict[str, Any]:
        service = _state(request)
        try:
            if not payload.confirmed:
                raise ConfigurationError("远程恢复需要 confirmed=true")
            record = resume_remote_pipeline(
                executor_id=executor_id,
                job_id=job_id,
                profile_path=service.profile_path,
            )
            return {
                "executor_id": executor_id,
                "job_id": job_id,
                "active_unit_name": record.active_unit_name,
                "resume_count": record.resume_count,
                "status": "resume-submitted",
            }
        except Exception as error:
            _raise_http(error)
            raise

    @app.post("/api/v1/remote-jobs/{executor_id}/{job_id}/sync")
    def remote_sync(
        executor_id: str,
        job_id: str,
        payload: RemoteSyncRequest,
        request: Request,
    ) -> dict[str, Any]:
        service = _state(request)
        try:
            if not payload.confirmed:
                raise ConfigurationError("远程结果同步需要 confirmed=true")
            record = next(
                (
                    item
                    for item in list_remote_job_records(executor_id=executor_id)
                    if item.submission.job_id == job_id
                ),
                None,
            )
            if record is None:
                raise ConfigurationError("远程任务记录不存在")
            destination = (
                service.registry.runs_root
                / record.submission.project_id
                / record.submission.run_id
            )
            report = sync_remote_pipeline(
                executor_id=executor_id,
                job_id=job_id,
                destination=destination,
                mode=payload.mode,
                profile_path=service.profile_path,
            )
            service.discover_runs()
            return {
                "status": "synced",
                "executor_id": executor_id,
                "job_id": job_id,
                "mode": report.mode,
                "file_count": report.file_count,
                "size_bytes": report.size_bytes,
                "run_manifest_sha256": report.run_manifest_sha256,
            }
        except Exception as error:
            _raise_http(error)
            raise

    @app.get("/api/v1/jobs")
    def jobs(request: Request) -> tuple[UiJobRecord, ...]:
        return _state(request).jobs.list()

    @app.get("/api/v1/jobs/{job_id}")
    def job(job_id: str, request: Request) -> UiJobRecord:
        try:
            return _state(request).jobs.load(job_id)
        except Exception as error:
            _raise_http(error)
            raise

    @app.post("/api/v1/jobs/{job_id}/drain")
    def drain(job_id: str, request: Request) -> UiJobRecord:
        try:
            return _state(request).jobs.request_drain(job_id)
        except Exception as error:
            _raise_http(error)
            raise

    @app.get("/api/v1/runs/{run_key}")
    def run(run_key: str, request: Request) -> Any:
        service = _state(request)
        try:
            return get_run_projection(
                service.registry.resolve(run_key),
                registry=service.registry,
                signer=service.signer,
            )
        except Exception as error:
            _raise_http(error)
            raise

    @app.get("/api/v1/runs/{run_key}/stages/{stage_number}")
    def stage(
        run_key: str,
        stage_number: Annotated[int, ApiPath(ge=1, le=7)],
        request: Request,
    ) -> Any:
        service = _state(request)
        try:
            return get_stage_projection(
                service.registry.resolve(run_key),
                stage_number,
                registry=service.registry,
                signer=service.signer,
            )
        except Exception as error:
            _raise_http(error)
            raise

    @app.get("/api/v1/runs/{run_key}/stages/{stage_number}/execution")
    def stage_execution(
        run_key: str,
        stage_number: Annotated[int, ApiPath(ge=1, le=7)],
        request: Request,
    ) -> Any:
        service = _state(request)
        try:
            if stage_number not in {4, 6}:
                raise ConfigurationError("执行进度投影只支持第4步或第6步")
            root = service.registry.resolve(run_key)
            runtime_snapshot = None
            try:
                snapshot = read_pipeline_progress(root)
                expected_stage = (
                    "04-pilot-generation"
                    if stage_number == 4
                    else "06-scale-generation-and-refolding"
                )
                if snapshot.stage_id == expected_stage:
                    runtime_snapshot = snapshot
            except EasyDesignError:
                pass
            return get_execution_progress(
                root,
                stage_number,
                runtime_snapshot=runtime_snapshot,
            )
        except Exception as error:
            _raise_http(error)
            raise

    @app.get("/api/v1/runs/{run_key}/stages/5/overview")
    def stage05_overview(run_key: str, request: Request) -> Any:
        service = _state(request)
        try:
            return get_filter_overview(
                service.registry.resolve(run_key),
                registry=service.registry,
            )
        except Exception as error:
            _raise_http(error)
            raise

    @app.get("/api/v1/runs/{run_key}/stages/5/strategies")
    def stage05_strategies(run_key: str, request: Request) -> Any:
        service = _state(request)
        try:
            return list_filter_strategies(
                service.registry.resolve(run_key),
                registry=service.registry,
                signer=service.signer,
            )
        except Exception as error:
            _raise_http(error)
            raise

    @app.get("/api/v1/runs/{run_key}/stages/5/metrics")
    def stage05_metrics(run_key: str, request: Request) -> Any:
        service = _state(request)
        try:
            return metric_catalog(service.registry.resolve(run_key))
        except Exception as error:
            _raise_http(error)
            raise

    @app.get("/api/v1/runs/{run_key}/stages/5/candidates")
    def stage05_candidates(
        run_key: str,
        request: Request,
        phase: Annotated[str, Query(pattern=r"^(pilot|expansion|full-target)$")] = "pilot",
        strategy_id: str | None = None,
        gate_status: str | None = None,
        failed_rule: str | None = None,
        page: Annotated[int, Query(ge=1)] = 1,
        page_size: Annotated[int, Query(ge=1, le=100)] = 50,
        sort_key: str = "candidate_id",
        sort_order: Annotated[str, Query(pattern=r"^(asc|desc)$")] = "asc",
    ) -> Any:
        service = _state(request)
        try:
            return list_filter_candidates(
                service.registry.resolve(run_key),
                phase=cast(Any, phase),
                strategy_id=strategy_id,
                gate_status=gate_status,
                failed_rule=failed_rule,
                page=page,
                page_size=page_size,
                sort_key=sort_key,
                sort_order=cast(Any, sort_order),
            )
        except Exception as error:
            _raise_http(error)
            raise

    @app.get("/api/v1/runs/{run_key}/stages/5/candidates/{candidate_id}")
    def stage05_candidate(
        run_key: str,
        candidate_id: str,
        request: Request,
        phase: Annotated[str, Query(pattern=r"^(pilot|expansion|full-target)$")] = "pilot",
    ) -> Any:
        service = _state(request)
        try:
            return get_filter_candidate(
                service.registry.resolve(run_key),
                candidate_id,
                phase=cast(Any, phase),
                registry=service.registry,
                signer=service.signer,
            )
        except Exception as error:
            _raise_http(error)
            raise

    @app.get("/api/v1/runs/{run_key}/replay")
    def replay(run_key: str, request: Request) -> Any:
        service = _state(request)
        try:
            return create_demo_replay(
                service.registry.resolve(run_key),
                registry=service.registry,
            )
        except Exception as error:
            _raise_http(error)
            raise

    @app.post("/api/v1/runs/{run_key}/clone")
    def clone(run_key: str, payload: CloneRunRequest, request: Request) -> dict[str, Any]:
        service = _state(request)
        try:
            path = clone_run_configuration(
                service.registry.resolve(run_key),
                service.projects_root / payload.project_id,
                project_id=payload.project_id,
            )
            return {
                "project_id": payload.project_id,
                "config": path.read_text(encoding="utf-8"),
                "status": "draft",
            }
        except Exception as error:
            _raise_http(error)
            raise

    @app.get("/api/v1/runs/{run_key}/decision")
    def decision(run_key: str, request: Request) -> dict[str, Any]:
        service = _state(request)
        try:
            value = show_decision(service.registry.resolve(run_key))
            return {
                "request": value.model_dump(mode="json"),
                "request_sha256": canonical_model_sha256(value),
            }
        except Exception as error:
            _raise_http(error)
            raise

    @app.post("/api/v1/runs/{run_key}/decision")
    def approve(
        run_key: str,
        payload: DecisionApprovalRequest,
        request: Request,
    ) -> UiJobRecord:
        service = _state(request)
        try:
            if not payload.confirmed:
                raise ConfigurationError("人工审批必须明确 confirmed=true")
            root = service.registry.resolve(run_key)
            pending = show_decision(root)
            approval = {
                "schema_version": "0.1",
                "decision_id": pending.decision_id,
                "request_revision": pending.revision,
                "request_sha256": canonical_model_sha256(pending),
                "selected_option_ids": payload.selected_option_ids,
                "approved_by": payload.approved_by,
                "acknowledgement": payload.acknowledgement,
            }
            approval_path = service.temporary_file(
                prefix="decision-approval",
                suffix=".yaml",
            )
            with approval_path.open("x", encoding="utf-8") as handle:
                yaml.safe_dump(approval, handle, allow_unicode=True, sort_keys=False)
            try:
                record = approve_decision(root, input_path=approval_path)
            finally:
                quarantine_if_workspace_path(
                    approval_path,
                    operation="ui-decision-approval",
                    reason="UI 决策审批 staging 已终止",
                )
            return service.jobs.launch(
                operation="decision",
                run_root=root,
                decision_record=record,
                profile_path=service.profile_path,
                confirmed=True,
            )
        except Exception as error:
            _raise_http(error)
            raise

    @app.get("/api/v1/runs/{run_key}/hotspots/review")
    def hotspot_review(
        run_key: str,
        request: Request,
        method: str | None = None,
    ) -> dict[str, str]:
        service = _state(request)
        selected_method: RegionMethod | None
        if method is None:
            selected_method = None
        elif method == "sasa":
            selected_method = RegionMethod.SASA_SURFACE_DIVERSITY
        elif method == "scannet":
            selected_method = RegionMethod.SCANNET_EPITOPE_NO_MSA
        else:
            raise HTTPException(status_code=400, detail="method 只允许 sasa 或 scannet")
        try:
            output = service.temporary_file(
                prefix="hotspot-review",
                suffix=".yaml",
            )
            try:
                export_hotspot_review(
                    service.registry.resolve(run_key),
                    method=selected_method,
                    output=output,
                )
                yaml_text = output.read_text(encoding="utf-8")
            finally:
                quarantine_if_workspace_path(
                    output,
                    operation="ui-hotspot-review",
                    reason="UI hotspot review staging 已终止",
                )
            return {"run_key": run_key, "yaml": yaml_text}
        except Exception as error:
            _raise_http(error)
            raise

    @app.get("/api/v1/runs/{run_key}/regions/editor")
    def region_editor(run_key: str, request: Request) -> Any:
        service = _state(request)
        try:
            return get_region_editor_projection(
                service.registry.resolve(run_key),
                run_key=run_key,
                signer=service.signer,
            )
        except Exception as error:
            _raise_http(error)
            raise

    @app.post("/api/v1/runs/{run_key}/regions/revise")
    def revise_regions(
        run_key: str,
        payload: RegionRevisionRequest,
        request: Request,
    ) -> dict[str, Any]:
        service = _state(request)
        try:
            if not payload.confirmed:
                raise ConfigurationError("重新选择区域必须明确 confirmed=true")
            if not payload.acknowledge_user_provided_regions:
                raise ConfigurationError("必须确认这些区域来自用户选择")
            if not payload.acknowledge_evidence_limitations:
                raise ConfigurationError("必须确认用户区域仍需生物学审阅")
            session = service.sessions.load(payload.session_id)
            source = service.registry.resolve(run_key)
            projection = get_region_editor_projection(
                source,
                run_key=run_key,
                signer=service.signer,
            )
            valid_labels = {item.label_seq_id for item in projection.residues}
            requested_labels = {
                int(value)
                for region in payload.regions
                for value in region.get("label_seq_ids", [])
            }
            missing = sorted(requested_labels - valid_labels)
            if missing:
                raise ConfigurationError(f"区域包含不存在的 label_seq_id: {missing}")
            project_root = (service.projects_root / session.project_id).resolve()
            try:
                project_root.relative_to(service.projects_root)
            except ValueError as error:
                raise PathPolicyError("产品会话项目路径逃出 projects_root") from error
            project_root.mkdir(parents=True, exist_ok=True)
            revision = len(session.config_revisions) + 1
            generated = project_root / (
                f"easydesign.stage02.rev{revision:04d}.yaml"
            )
            materialize_continuation_config(
                source_run_root=source,
                destination=generated,
                stage_number=2,
                execution_mode=payload.execution_mode,
                continue_after_stage=1,
                options={
                    "mode": "user-provided",
                    "regions": payload.regions,
                    "approved_by": payload.approved_by,
                    "acknowledge_user_provided_regions": True,
                    "acknowledge_evidence_limitations": True,
                },
            )
            session = service.sessions.add_config_revision(
                session.session_id,
                stage_number=2,
                config_path=generated,
            )
            service.activate_project_config(session.project_id, generated)
            selected_run_id = payload.run_id or (
                datetime.now(tz=UTC).strftime("%Y%m%dt%H%M%Sz").lower()
                + "-stage02-regions"
            )
            job = service.jobs.launch(
                operation="run",
                config_path=generated,
                run_root=source,
                profile_path=service.profile_path,
                runs_root=service.registry.runs_root,
                run_id=selected_run_id,
                continue_after_stage=1,
                session_id=session.session_id,
                session_root=service.sessions.root,
                stage_number=2,
                confirmed=True,
            )
            session = service.sessions.update_status(
                session.session_id,
                status="running",
                current_stage=2,
            )
            return {
                "session": session.model_dump(mode="json"),
                "job": job.model_dump(mode="json"),
            }
        except Exception as error:
            _raise_http(error)
            raise

    @app.post("/api/v1/runs/{run_key}/hotspots/approve")
    def hotspot_approve(
        run_key: str,
        payload: HotspotApprovalRequest,
        request: Request,
    ) -> dict[str, str]:
        service = _state(request)
        try:
            if not payload.confirmed:
                raise ConfigurationError("Hotspot 审批必须明确 confirmed=true")
            approval_path = service.temporary_file(
                prefix="hotspot-approval",
                suffix=".yaml",
            )
            with approval_path.open("x", encoding="utf-8") as handle:
                handle.write(payload.yaml_text)
            try:
                approve_hotspots(
                    service.registry.resolve(run_key),
                    input_path=approval_path,
                )
            finally:
                quarantine_if_workspace_path(
                    approval_path,
                    operation="ui-hotspot-approval",
                    reason="UI hotspot approval staging 已终止",
                )
            return {
                "status": "approved",
                "run_key": run_key,
                "next_action": "resume",
            }
        except Exception as error:
            _raise_http(error)
            raise

    @app.post("/api/v1/runs/{run_key}/continue/{next_stage}")
    def continue_to_next_stage(
        run_key: str,
        next_stage: int,
        payload: ContinuationRequest,
        request: Request,
    ) -> dict[str, Any]:
        service = _state(request)
        try:
            if not payload.confirmed:
                raise ConfigurationError("继续下一阶段必须明确 confirmed=true")
            if payload.stage_number != next_stage:
                raise ConfigurationError("URL stage 与请求 stage_number 不一致")
            session = service.sessions.load(payload.session_id)
            source = service.registry.resolve(run_key)
            project_root = (service.projects_root / session.project_id).resolve()
            try:
                project_root.relative_to(service.projects_root)
            except ValueError as error:
                raise PathPolicyError("产品会话项目路径逃出 projects_root") from error
            project_root.mkdir(parents=True, exist_ok=True)
            revision = len(session.config_revisions) + 1
            generated = project_root / (
                f"easydesign.stage{next_stage:02d}.rev{revision:04d}.yaml"
            )
            # Stepwise runs remain open while the user inspects each completed
            # stage.  Continuing therefore depends on the verified succeeded
            # Stage prefix, not on the whole RunManifest being terminal.
            continue_after_stage = next_stage - 1
            materialize_continuation_config(
                source_run_root=source,
                destination=generated,
                stage_number=next_stage,
                execution_mode=payload.execution_mode,
                options=payload.options,
                continue_after_stage=continue_after_stage,
            )
            try:
                session = service.sessions.add_config_revision(
                    session.session_id,
                    stage_number=next_stage,
                    config_path=generated,
                )
                service.activate_project_config(session.project_id, generated)
                job = service.jobs.launch(
                    operation="run",
                    config_path=generated,
                    run_root=source,
                    profile_path=service.profile_path,
                    runs_root=service.registry.runs_root,
                    run_id=(
                        payload.run_id
                        or (
                            datetime.now(tz=UTC)
                            .strftime("%Y%m%dt%H%M%Sz")
                            .lower()
                            + "-stage02-selection"
                        )
                        if next_stage == 2
                        else payload.run_id
                    ),
                    continue_after_stage=continue_after_stage,
                    session_id=session.session_id,
                    session_root=service.sessions.root,
                    stage_number=next_stage,
                    confirmed=True,
                )
                session = service.sessions.update_status(
                    session.session_id,
                    status="running",
                    current_stage=next_stage,
                )
            except Exception:
                quarantine_if_workspace_path(
                    generated,
                    operation=f"ui-stage{next_stage:02d}-continuation",
                    reason="UI continuation 未能启动",
                )
                raise
            return {
                "session": session.model_dump(mode="json"),
                "job": job.model_dump(mode="json"),
            }
        except Exception as error:
            _raise_http(error)
            raise

    @app.post("/api/v1/runs/{run_key}/resume")
    def resume(
        run_key: str,
        payload: ConfirmedActionRequest,
        request: Request,
    ) -> UiJobRecord:
        service = _state(request)
        try:
            return service.jobs.launch(
                operation="resume",
                run_root=service.registry.resolve(run_key),
                profile_path=service.profile_path,
                confirmed=payload.confirmed,
            )
        except Exception as error:
            _raise_http(error)
            raise

    @app.get("/api/v1/runs/{run_key}/events/history")
    def event_history(run_key: str, request: Request) -> dict[str, Any]:
        service = _state(request)
        try:
            events = [
                json.loads(line)
                for line in stream_run_events(service.registry.resolve(run_key))
            ]
            return {"events": events}
        except Exception as error:
            _raise_http(error)
            raise

    @app.get("/api/v1/runs/{run_key}/events")
    async def events(run_key: str, request: Request) -> StreamingResponse:
        service = _state(request)
        root = service.registry.resolve(run_key)

        async def generate() -> AsyncIterator[str]:
            last = ""
            for _ in range(180):
                if await request.is_disconnected():
                    return
                try:
                    snapshot = await asyncio.to_thread(read_pipeline_progress, root)
                    if snapshot.stage_id in {
                        "04-pilot-generation",
                        "06-scale-generation-and-refolding",
                    }:
                        stage_number = 4 if snapshot.stage_id.startswith("04-") else 6
                        execution_projection = await asyncio.to_thread(
                            get_execution_progress,
                            root,
                            stage_number,
                            runtime_snapshot=snapshot,
                        )
                        payload = execution_projection.model_dump_json()
                    else:
                        payload = snapshot.model_dump_json()
                    terminal = snapshot.status in {"succeeded", "scientific-stop", "failed"}
                except EasyDesignError:
                    run_projection = await asyncio.to_thread(
                        get_run_projection,
                        root,
                        registry=service.registry,
                        signer=service.signer,
                    )
                    payload = run_projection.model_dump_json()
                    terminal = run_projection.status in {"succeeded", "failed"}
                if payload != last:
                    yield f"event: progress\ndata: {payload}\n\n"
                    last = payload
                if terminal:
                    return
                await asyncio.sleep(2)

        return StreamingResponse(generate(), media_type="text/event-stream")

    @app.post("/api/v1/runs/{run_key}/draft-order-package")
    def order_package(run_key: str, request: Request) -> Any:
        service = _state(request)
        try:
            return create_draft_order_package(
                service.registry.resolve(run_key),
                registry=service.registry,
                signer=service.signer,
            )
        except Exception as error:
            _raise_http(error)
            raise

    @app.get("/api/v1/artifacts/{token}")
    def artifact(token: str, request: Request, download: bool = False) -> FileResponse:
        service = _state(request)
        try:
            claims = service.signer.verify(token)
            root = service.registry.resolve(claims.run_key)
            reference = ArtifactRef(
                artifact_id="ui-artifact",
                role="ui-artifact",
                relative_path=claims.relative_path,
                file_format="binary",
                sha256=claims.sha256,
                size_bytes=claims.size_bytes,
            )
            path = reference.verify(root)
            media_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
            return FileResponse(
                path,
                media_type=media_type,
                filename=path.name if download else None,
                content_disposition_type="attachment" if download else "inline",
            )
        except Exception as error:
            _raise_http(error)
            raise

    ui_root = Path(__file__).resolve().parent / "static"
    molstar_root = (
        Path(easydesign.__file__).resolve().parent
        / "reporting"
        / "static"
        / "target_viewer"
        / "vendor"
        / "molstar"
    )
    app.mount("/molstar", StaticFiles(directory=molstar_root), name="molstar")
    app.mount("/assets", StaticFiles(directory=ui_root / "assets"), name="ui-assets")

    @app.get("/{path:path}")
    def frontend(path: str) -> FileResponse:
        if path.startswith("api/"):
            raise HTTPException(status_code=404)
        return FileResponse(ui_root / "index.html")

    return app


def serve_ui(
    *,
    runs_root: Path,
    projects_root: Path | None = None,
    profile_path: Path | None = None,
    job_root: Path | None = None,
    port: int = 8765,
    open_browser: bool = False,
) -> None:
    if port < 1 or port > 65535:
        raise ConfigurationError("UI port 必须在 1–65535")
    application = create_ui_app(
        runs_root=runs_root,
        projects_root=projects_root,
        profile_path=profile_path,
        job_root=job_root,
    )
    url = f"http://{LOCAL_HOST}:{port}"
    print(f"EasyDesign 科研工作台：{url}")
    print(f"远程服务器请使用：ssh -L {port}:127.0.0.1:{port} USER@SERVER")
    if open_browser:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    uvicorn.run(application, host=LOCAL_HOST, port=port, log_level="info")
