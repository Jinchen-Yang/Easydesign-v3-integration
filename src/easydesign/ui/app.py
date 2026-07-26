"""FastAPI localhost gateway；浏览器不直接接触机器路径或科学实现。"""

from __future__ import annotations

import asyncio
import base64
import json
import mimetypes
import tempfile
import threading
import webbrowser
from collections.abc import AsyncIterator
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
from easydesign.orchestration import (
    approve_hotspots,
    diagnose_runtime,
    export_hotspot_review,
    initialize_project,
    list_runs,
    read_pipeline_progress,
    validate_run_configuration,
)
from easydesign.orchestration.decisions import approve_decision, show_decision
from easydesign.stages.s02_hotspot_discovery import RegionMethod

from .execution import get_execution_progress
from .jobs import UiJobController, clone_run_configuration
from .models import UiJobRecord
from .projections import (
    create_demo_replay,
    create_draft_order_package,
    get_project_projection,
    get_run_projection,
    get_stage_projection,
    stream_run_events,
)
from .security import ArtifactTokenSigner, UiRunRegistry
from .stage05 import (
    get_filter_candidate,
    get_filter_overview,
    list_filter_candidates,
    list_filter_strategies,
    metric_catalog,
)

LOCAL_HOST = "127.0.0.1"


class UploadRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    filename: str = Field(min_length=1, max_length=255)
    content_base64: str


class UploadReceipt(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    upload_token: str
    filename: str
    size_bytes: int


class ProjectCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: str
    target_id: str | None = None
    source_type: str
    source_value: str
    taxon_id: int | None = None
    chain: str | None = None
    execution_mode: str = "review-gated"
    stop_after_stage: int = Field(default=1, ge=1, le=7)
    stage02_method: str | None = None
    source_run_key: str | None = None


class ConfigUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    yaml_text: str = Field(min_length=1, max_length=1_000_000)


class PreflightRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: str


class LaunchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: str
    run_id: str | None = None
    confirmed: bool = False


class CloneRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: str


class ConfirmedActionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

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
        self.registry = UiRunRegistry(runs_root)
        self.signer = ArtifactTokenSigner()
        self.projects_root = projects_root.expanduser().resolve()
        self.projects_root.mkdir(parents=True, exist_ok=True)
        self.profile_path = None if profile_path is None else profile_path.expanduser().resolve()
        self.jobs = UiJobController(job_root)
        self.upload_root = self.projects_root / ".ui-uploads"
        self.upload_root.mkdir(parents=True, exist_ok=True)
        self.uploads: dict[str, Path] = {}

    def project_config(self, project_id: str) -> Path:
        root = (self.projects_root / project_id).resolve()
        try:
            root.relative_to(self.projects_root)
        except ValueError as error:
            raise PathPolicyError("Project ID 逃出 UI projects root") from error
        path = root / "easydesign.yaml"
        if not path.is_file():
            raise ConfigurationError(f"项目配置不存在: {project_id}")
        return path

    def projects(self) -> tuple[str, ...]:
        return tuple(
            sorted(
                path.parent.name
                for path in self.projects_root.glob("*/easydesign.yaml")
                if path.is_file()
            )
        )

    def discover_runs(self) -> None:
        for summary in list_runs(self.registry.runs_root):
            if summary.integrity_status == "verified":
                self.registry.register(summary.path)


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
            "font-src 'self' data:; connect-src 'self'; worker-src 'self' blob:; "
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
        if len(content) > 64 * 1024 * 1024:
            raise HTTPException(status_code=413, detail="单文件上限为 64 MiB")
        token = f"upload-{uuid4().hex}"
        target = service.upload_root / f"{token}-{filename}"
        target.write_bytes(content)
        service.uploads[token] = target
        return UploadReceipt(upload_token=token, filename=filename, size_bytes=len(content))

    @app.post("/api/v1/projects")
    def initialize(payload: ProjectCreateRequest, request: Request) -> dict[str, Any]:
        service = _state(request)
        try:
            source_value = payload.source_value
            kwargs: dict[str, Any] = {
                "project_root": service.projects_root / payload.project_id,
                "project_id": payload.project_id,
                "target_id": payload.target_id,
                "execution_mode": payload.execution_mode,
                "stop_after_stage": payload.stop_after_stage,
                "stage02_method": payload.stage02_method,
            }
            if payload.source_type == "local-file":
                try:
                    kwargs["target"] = service.uploads[source_value]
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
            return {
                "project_id": payload.project_id,
                "config": outcome.config_path.read_text(encoding="utf-8"),
                "status": "draft",
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
            path = service.project_config(project_id)
            temporary = path.with_suffix(".ui-validation.yaml")
            temporary.write_text(payload.yaml_text, encoding="utf-8")
            try:
                plan = validate_run_configuration(
                    temporary,
                    profile_path=service.profile_path,
                )
            finally:
                temporary.unlink(missing_ok=True)
            path.write_text(payload.yaml_text, encoding="utf-8")
            return {"status": "valid", "plan": plan.model_dump(mode="json")}
        except Exception as error:
            _raise_http(error)
            raise

    @app.post("/api/v1/preflight")
    def preflight(payload: PreflightRequest, request: Request) -> dict[str, Any]:
        service = _state(request)
        try:
            config = service.project_config(payload.project_id)
            plan = validate_run_configuration(config, profile_path=service.profile_path)
            diagnostic = diagnose_runtime(
                profile_path=service.profile_path,
                config_path=config,
            )
            return {
                "plan": plan.model_dump(mode="json"),
                "diagnostic": diagnostic.model_dump(mode="json"),
            }
        except Exception as error:
            _raise_http(error)
            raise

    @app.post("/api/v1/jobs")
    def launch(payload: LaunchRequest, request: Request) -> UiJobRecord:
        service = _state(request)
        try:
            return service.jobs.launch(
                operation="run",
                config_path=service.project_config(payload.project_id),
                profile_path=service.profile_path,
                run_id=payload.run_id,
                confirmed=payload.confirmed,
            )
        except Exception as error:
            _raise_http(error)
            raise

    @app.get("/api/v1/jobs")
    def jobs(request: Request) -> tuple[UiJobRecord, ...]:
        return _state(request).jobs.list()

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
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                suffix=".yaml",
                prefix="easydesign-ui-decision-",
                delete=False,
            ) as handle:
                yaml.safe_dump(approval, handle, allow_unicode=True, sort_keys=False)
                approval_path = Path(handle.name)
            try:
                record = approve_decision(root, input_path=approval_path)
            finally:
                approval_path.unlink(missing_ok=True)
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
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                suffix=".yaml",
                prefix="easydesign-ui-hotspots-",
                delete=False,
            ) as handle:
                output = Path(handle.name)
            try:
                export_hotspot_review(
                    service.registry.resolve(run_key),
                    method=selected_method,
                    output=output,
                )
                yaml_text = output.read_text(encoding="utf-8")
            finally:
                output.unlink(missing_ok=True)
            return {"run_key": run_key, "yaml": yaml_text}
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
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                suffix=".yaml",
                prefix="easydesign-ui-hotspots-approval-",
                delete=False,
            ) as handle:
                handle.write(payload.yaml_text)
                approval_path = Path(handle.name)
            try:
                approve_hotspots(
                    service.registry.resolve(run_key),
                    input_path=approval_path,
                )
            finally:
                approval_path.unlink(missing_ok=True)
            return {
                "status": "approved",
                "run_key": run_key,
                "next_action": "resume",
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
    port: int = 8765,
    open_browser: bool = False,
) -> None:
    if port < 1 or port > 65535:
        raise ConfigurationError("UI port 必须在 1–65535")
    application = create_ui_app(
        runs_root=runs_root,
        projects_root=projects_root,
        profile_path=profile_path,
    )
    url = f"http://{LOCAL_HOST}:{port}"
    print(f"EasyDesign 科研工作台：{url}")
    print(f"远程服务器请使用：ssh -L {port}:127.0.0.1:{port} USER@SERVER")
    if open_browser:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    uvicorn.run(application, host=LOCAL_HOST, port=port, log_level="info")
