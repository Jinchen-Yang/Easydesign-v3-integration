"""FastAPI localhost gateway；浏览器不直接接触机器路径或科学实现。"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import mimetypes
import re
import shutil
import threading
import webbrowser
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any, Literal, cast
from uuid import uuid4

import httpx
import uvicorn
import yaml  # type: ignore[import-untyped]
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi import Path as ApiPath
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, SecretStr

import easydesign
from easydesign.backends.executors.local_multi_gpu import NvidiaSmiProbe
from easydesign.core import (
    ArtifactRef,
    ConfigurationError,
    EasyDesignError,
    PathPolicyError,
    canonical_model_sha256,
)
from easydesign.core.artifacts import ID_PATTERN
from easydesign.core.hashing import sha256_bytes, sha256_file
from easydesign.orchestration import (
    RemoteExecutorRegistry,
    approve_hotspots,
    archive_project,
    diagnose_runtime,
    export_hotspot_review,
    initialize_project,
    install_public_key_with_password,
    list_managed_remote_submissions,
    list_project_catalog,
    list_remote_executor_ids,
    list_remote_job_records,
    list_runs,
    load_verified_project_scale_evidence,
    materialize_continuation_config,
    observe_managed_pipeline,
    observe_remote_pipeline,
    probe_managed_executor,
    probe_pending_managed_executor,
    probe_remote_executor,
    public_key_install_command,
    read_pipeline_progress,
    restore_project,
    resume_remote_pipeline,
    scan_host_identity,
    stage_form_definition,
    submit_managed_pipeline,
    submit_remote_pipeline,
    sync_remote_pipeline,
    validate_run_configuration,
)
from easydesign.orchestration.decisions import approve_decision, show_decision
from easydesign.orchestration.execution_targets import (
    GpuLeaseStore,
    LocalCurrentHostTarget,
)
from easydesign.orchestration.runtime_setup import (
    SETUP_COMPONENT_IDS,
    asset_status,
    environment_status,
    initialize_workspace_metadata,
    setup_plan,
)
from easydesign.orchestration.setup_jobs import (
    launch_setup_job,
    list_setup_jobs,
)
from easydesign.orchestration.task_tracking import (
    atomic_dump_runtime_model,
    load_latest_runtime_model,
)
from easydesign.safe_writes import quarantine_if_workspace_path, read_last_text_line
from easydesign.stages.s02_hotspot_discovery import RegionMethod
from easydesign.workspace_context import WorkspaceContext

from .access import (
    StageLockedError,
    assert_not_locked_by_downstream,
    assert_stage_configurable,
    highest_accepted_stage,
)
from .audit import UiAuditLogger
from .browser_pymol_assets import verify_browser_pymol_assets
from .execution import get_execution_progress
from .jobs import UiJobController
from .models import (
    DesignSession,
    ProjectMetadata,
    SelfTestRecord,
    UiJobRecord,
    UploadReceipt,
)
from .projections import (
    create_demo_replay,
    create_draft_order_package,
    get_project_draft_projection,
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
from .structure_interactions import (
    AssistantProposal,
    AssistantProviderStore,
    ChatPyMolEdit,
    ReferenceStructure,
    RegionEditOperation,
    SceneVersion,
    SceneVersionConflictError,
    ScientificAnalysisPlan,
    StructureInteractionStore,
    derive_scene_summary,
    normalize_regions,
    request_assistant_pml_edit,
    split_pml_commands,
)
from .uploads import UploadStore

LOCAL_HOST = "127.0.0.1"
MAX_UPLOAD_BYTES = 64 * 1024 * 1024


def _pairing_projection(record: Any, *, include_public_key: bool = False) -> dict[str, Any]:
    """Expose pairing facts without leaking controller filesystem paths."""

    projection = {
        "executor_id": record.executor_id,
        "controller_id": record.controller_id,
        "state": record.state,
        # All public executor projections use pairing_state.  Keep state for
        # compatibility with the pairing action responses, but do not make
        # Stage 04/06 consumers translate between the two endpoint shapes.
        "pairing_state": record.state,
        "host": record.host,
        "port": record.port,
        "user": record.user,
        "host_fingerprint": record.host_identity.fingerprint,
        "public_key_fingerprint": record.public_key_fingerprint,
        "managed_worker_root": record.managed_worker_root,
        "updated_at": record.updated_at.isoformat(),
    }
    if include_public_key:
        projection["public_key"] = record.public_key
    return projection


def _suggest_project_id(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9._-]+", "-", value.strip().lower()).strip("-._")
    return normalized[:128] or "new-design"


class UploadRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    filename: str = Field(min_length=1, max_length=255)
    content_base64: str


class ProjectCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: str
    target_id: str | None = None
    source_type: str
    source_value: str
    taxon_id: int | None = None
    chain: str | None = None
    execution_mode: Literal["unattended", "review-gated"] = "review-gated"
    design_intent: str = "exploratory"
    stop_after_stage: int = Field(default=1, ge=1, le=7)
    stage06_candidate_count: int = Field(default=50_000, ge=1)
    stage02_method: str | None = None
    source_run_key: str | None = None
    design_mode: Literal[
        "full-workflow", "stepwise", "developer-smoke"
    ] = "full-workflow"
    session_id: str | None = None


class DesignSessionCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: str
    design_mode: Literal["full-workflow", "stepwise", "developer-smoke"]
    execution_mode: Literal["unattended", "review-gated"] = "review-gated"


class ContinuationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str
    stage_number: int = Field(ge=2, le=7)
    execution_mode: Literal["unattended", "review-gated"] = "review-gated"
    options: dict[str, Any] = Field(default_factory=dict)
    run_id: str | None = None
    executor_id: str | None = None
    controller_id: str | None = None
    maximum_gpus: int | None = Field(default=None, ge=1, le=8)
    sync_mode: Literal["metadata", "review", "complete"] = "review"
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

    mode: str = Field(default="review", pattern=r"^(metadata|review|complete)$")
    confirmed: bool = False


class RemoteHostScanRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    host: str = Field(min_length=1)
    port: int = Field(default=22, ge=1, le=65535)


class RemotePairBeginRequest(RemoteHostScanRequest):
    executor_id: str = Field(pattern=ID_PATTERN)
    controller_id: str = Field(pattern=ID_PATTERN)
    user: str = Field(default="root", min_length=1)
    confirmed_host_fingerprint: str = Field(min_length=8)


class RemotePairActionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    confirmed: bool = False


class RemotePairPasswordRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    password: SecretStr
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


class StructureSessionCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stage_number: Literal[1, 2]


class AssistantMessageRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: str = Field(min_length=1, max_length=20_000)


class PmlRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pml: str = Field(min_length=1, max_length=2_000_000)
    source: Literal["viewer", "expert-console"] = "expert-console"
    base_version_id: str | None = None


class ProposalApplyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    confirmed: bool = False


class SceneVersionRestoreRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    base_version_id: str | None = None
    confirmed: bool = False


class ReferenceUploadRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    upload_token: str = Field(min_length=1, max_length=256)
    object_name: str | None = Field(default=None, min_length=1, max_length=64)
    confirmed: bool = False


class ReferenceRcsbRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rcsb_id: str = Field(pattern=r"^[0-9A-Za-z]{4}$")
    object_name: str | None = Field(default=None, min_length=1, max_length=64)
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
        self.ui_state_root = self.workspace.runtime_root / "state" / "ui"
        self.ui_state_root.mkdir(parents=True, exist_ok=True)
        self.signer = ArtifactTokenSigner.from_file(
            self.ui_state_root / "artifact-token-secret.bin"
        )
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
        self.sessions = DesignSessionStore(self.ui_state_root / "design-sessions")
        self.structure_sessions = StructureInteractionStore(self.projects_root)
        self.assistant_providers = AssistantProviderStore(
            self.workspace.runtime_root / "secrets" / "structure-assistant"
        )
        self.self_tests = SelfTestStore(
            self.ui_state_root / "self-tests",
            self.registry.runs_root,
            workspace=self.workspace,
            profile_path=self.profile_path,
        )
        self.audit = UiAuditLogger(self.workspace)
        self.upload_store = UploadStore(self.workspace)
        self.upload_root = self.upload_store.file_root
        self.temporary_root = self.workspace.runtime_root / "tmp" / "ui"
        self.temporary_root.mkdir(parents=True, exist_ok=True)

    def project_root(self, project_id: str, *, require_exists: bool = True) -> Path:
        root = (self.projects_root / project_id).resolve()
        try:
            root.relative_to(self.projects_root)
        except ValueError as error:
            raise PathPolicyError("Project ID 逃出 UI projects root") from error
        if require_exists and not root.is_dir():
            raise ConfigurationError(f"项目目录不存在: {project_id}")
        return root

    def project_preflight(self, project_id: str) -> dict[str, Any]:
        project_id = project_id.strip()
        if re.fullmatch(ID_PATTERN, project_id) is None:
            return {
                "available": False,
                "project_id": project_id,
                "reason": (
                    "项目名称只能使用小写字母、数字、点、下划线和连字符，"
                    "并且必须以小写字母或数字开头"
                ),
                "existing_project": None,
                "suggested_project_id": _suggest_project_id(project_id),
            }
        root = self.project_root(project_id, require_exists=False)
        if root.exists():
            return {
                "available": False,
                "project_id": project_id,
                "reason": "项目名称已存在，禁止覆盖",
                "existing_project": project_id,
                "suggested_project_id": (
                    f"{project_id}-{datetime.now(tz=UTC).strftime('%Y%m%d-%H%M%S')}"
                ),
            }
        return {
            "available": True,
            "project_id": project_id,
            "reason": "项目名称可用",
            "existing_project": None,
            "suggested_project_id": None,
        }

    def project_config(self, project_id: str) -> Path:
        root = self.project_root(project_id)
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
        root = self.project_root(project_id)
        revisions = root / "config-revisions"
        revisions.mkdir(parents=True, exist_ok=True)
        self.audit.event(
            "dir.created",
            operation_id=f"config-publish-{project_id}",
            project_id=project_id,
            path=revisions,
            message="project config revisions directory ensured",
        )
        existing = sorted(revisions.glob("easydesign.rev-*.yaml"))
        revision = len(existing) + 1
        destination = revisions / f"easydesign.rev-{revision:06d}.yaml"
        with destination.open("x", encoding="utf-8") as handle:
            handle.write(yaml_text)
            if not yaml_text.endswith("\n"):
                handle.write("\n")
        self.audit.event(
            "config.revision.created",
            operation_id=f"config-publish-{project_id}",
            project_id=project_id,
            path=destination,
            status="created",
        )
        self.activate_project_config(project_id, destination)
        return destination

    def activate_project_config(self, project_id: str, config_path: Path) -> None:
        root = self.project_root(project_id)
        selected = config_path.resolve()
        try:
            relative = selected.relative_to(root)
        except ValueError as error:
            raise PathPolicyError("项目配置必须位于对应项目目录内") from error
        if not selected.is_file():
            raise ConfigurationError("准备激活的项目配置不存在")
        with (root / "CONFIG_CURRENT").open("a", encoding="utf-8") as handle:
            handle.write(f"{relative.as_posix()}\n")
        self.audit.event(
            "config.activated",
            operation_id=f"config-activate-{project_id}",
            project_id=project_id,
            path=selected,
            status="active",
        )

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

    def project_run_roots(self, project_id: str) -> tuple[Path, ...]:
        return tuple(
            item.path
            for item in list_runs(self.registry.runs_root)
            if item.integrity_status == "verified" and item.project_id == project_id
        )

    def accepted_job_for_run(
        self,
        run_key: str,
    ) -> tuple[int | None, datetime | None, str | None]:
        accepted = [
            item
            for item in self.jobs.list()
            if item.accepted_run_key == run_key and item.stage_number is not None
        ]
        if not accepted:
            return None, None, None
        selected = max(
            accepted,
            key=lambda item: (int(item.stage_number or 0), item.created_at),
        )
        return selected.stage_number, selected.created_at, selected.status

    def accepted_jobs_by_run(
        self,
    ) -> dict[str, tuple[int | None, datetime | None, str | None]]:
        values: dict[
            str,
            tuple[int | None, datetime | None, str | None],
        ] = {}
        for item in self.jobs.list():
            if item.accepted_run_key is None or item.stage_number is None:
                continue
            previous = values.get(item.accepted_run_key)
            if previous is None or int(item.stage_number) >= int(previous[0] or 0):
                values[item.accepted_run_key] = (
                    item.stage_number,
                    item.created_at,
                    item.status,
                )
        return values

    def accepted_job_for_project(
        self,
        project_id: str,
    ) -> tuple[int | None, datetime | None]:
        accepted = [
            item
            for item in self.jobs.list()
            if item.project_id == project_id and item.stage_number is not None
        ]
        if not accepted:
            return None, None
        selected = max(
            accepted,
            key=lambda item: (int(item.stage_number or 0), item.created_at),
        )
        return selected.stage_number, selected.created_at

    def assert_stage_configurable(self, run_key: str, stage_number: int) -> None:
        accepted_stage, accepted_at, _ = self.accepted_job_for_run(run_key)
        assert_stage_configurable(
            self.registry.resolve(run_key),
            stage_number,
            accepted_job_stage=accepted_stage,
            accepted_job_at=accepted_at,
        )

    def assert_session_uses_latest_run(
        self,
        session: DesignSession,
        run_key: str,
    ) -> None:
        latest = session.run_lineage[-1] if session.run_lineage else None
        if latest is None or latest == run_key:
            return
        raise ConfigurationError(
            "当前页面不是这个产品会话的最新运行；请打开最新运行后再继续。"
            "如需重新配置已经完成的阶段，请从新建设计显式创建独立版本。"
        )

    def assert_not_locked_by_downstream(
        self,
        run_key: str,
        stage_number: int,
    ) -> None:
        accepted_stage, accepted_at, _ = self.accepted_job_for_run(run_key)
        assert_not_locked_by_downstream(
            self.registry.resolve(run_key),
            stage_number,
            accepted_job_stage=accepted_stage,
            accepted_job_at=accepted_at,
        )

    def assert_project_is_draft(self, project_id: str) -> None:
        accepted_job_stage, accepted_job_at = self.accepted_job_for_project(
            project_id
        )
        if accepted_job_stage is not None:
            raise StageLockedError(
                stage_number=accepted_job_stage,
                locked_by_stage=accepted_job_stage,
                locked_at=accepted_job_at,
                reason=(
                    f"项目 {project_id} 已经受理第{accepted_job_stage}步执行，"
                    "原项目配置只读。如需改变输入，请从“新建设计”创建不同名称的"
                    "独立项目。"
                ),
            )
        roots = self.project_run_roots(project_id)
        if not roots:
            return
        accepted = [
            (highest_accepted_stage(root)[0], root)
            for root in roots
        ]
        highest, _ = max(accepted, key=lambda item: item[0])
        raise StageLockedError(
            stage_number=max(1, highest),
            locked_by_stage=max(1, highest),
            locked_at=None,
            reason=(
                f"项目 {project_id} 已经产生正式运行记录，原项目配置只读。"
                "如需改变输入或重新运行，请从“新建设计”创建不同名称的独立项目。"
            ),
        )

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
        job = launch_setup_job(
            self.workspace,
            minimal=minimal,
            component=component,
            accepted_license_ids=set(accepted_license_ids),
        )
        return job.model_dump(mode="json")

    def setup_jobs(self) -> list[dict[str, Any]]:
        return [
            item.model_dump(mode="json")
            for item in list_setup_jobs(self.workspace)
        ]


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
    if isinstance(error, StageLockedError):
        raise HTTPException(status_code=409, detail=error.detail()) from error
    if isinstance(error, SceneVersionConflictError):
        raise HTTPException(status_code=409, detail=str(error)) from error
    if isinstance(error, PathPolicyError):
        raise HTTPException(status_code=403, detail=str(error)) from error
    if isinstance(error, (ConfigurationError, EasyDesignError, ValueError)):
        raise HTTPException(status_code=400, detail=str(error)) from error
    raise error


def _resolve_region_operation(
    operation: RegionEditOperation,
    residues: tuple[Any, ...],
) -> tuple[int, ...]:
    resolved: list[int] = []
    for selector in operation.residues:
        matches: list[int] = []
        if operation.numbering == "label":
            if selector.isdigit():
                matches = [
                    item.label_seq_id
                    for item in residues
                    if item.label_seq_id == int(selector)
                ]
        elif operation.numbering == "sequence":
            if selector.isdigit():
                matches = [
                    item.label_seq_id
                    for item in residues
                    if item.sequence_index == int(selector)
                ]
        elif operation.numbering == "uniprot":
            if selector.isdigit():
                matches = [
                    item.label_seq_id
                    for item in residues
                    if item.reference_position == int(selector)
                ]
        else:
            selected_chain = operation.chain
            matches = [
                item.label_seq_id
                for item in residues
                if item.auth_residue_id == selector
                and (
                    selected_chain is None
                    or item.auth_chain_id == selected_chain
                )
            ]
        if len(matches) != 1:
            raise ConfigurationError(
                f"残基选择器无法唯一映射: numbering={operation.numbering}, "
                f"selector={selector}"
            )
        resolved.append(matches[0])
    return tuple(resolved)


def _apply_region_operations(
    current_regions: dict[str, tuple[int, ...]],
    operations: tuple[RegionEditOperation, ...],
    residues: tuple[Any, ...],
) -> dict[str, tuple[int, ...]]:
    values = {
        region_id: set(current_regions.get(region_id, ()))
        for region_id in ("A", "B", "C")
    }
    for operation in operations:
        selected = set(_resolve_region_operation(operation, residues))
        if operation.operation == "clear":
            values[operation.region_id] = set()
            continue
        if operation.operation == "replace":
            values[operation.region_id] = set(selected)
            for other in ("A", "B", "C"):
                if other != operation.region_id:
                    values[other].difference_update(selected)
            continue
        for residue in selected:
            if operation.operation == "remove":
                values[operation.region_id].discard(residue)
            elif (
                operation.operation == "toggle"
                and residue in values[operation.region_id]
            ):
                values[operation.region_id].discard(residue)
            else:
                for other in ("A", "B", "C"):
                    values[other].discard(residue)
                values[operation.region_id].add(residue)
    return normalize_regions(
        {
            region_id: tuple(sorted(selected))
            for region_id, selected in values.items()
        }
    )


def _author_selector_from_labels(
    residues: tuple[Any, ...],
    labels: tuple[int, ...],
) -> str:
    requested = set(labels)
    by_chain: dict[str, list[str]] = {}
    for residue in residues:
        if residue.label_seq_id not in requested:
            continue
        chain = residue.auth_chain_id or "A"
        value = _author_residue_token(
            residue.auth_residue_id,
            residue.insertion_code,
        )
        by_chain.setdefault(chain, []).append(value)
    clauses = [
        f"(chain {chain} and resi {'+'.join(sorted(set(values)))})"
        for chain, values in sorted(by_chain.items())
        if values
    ]
    return " or ".join(clauses) if clauses else "none"


def _author_residue_token(
    auth_residue_id: str,
    insertion_code: str | None,
) -> str:
    value = str(auth_residue_id)
    code = insertion_code or ""
    if code and not value.upper().endswith(code.upper()):
        value += code
    return value


def _target_reference(region_projection: Any) -> ReferenceStructure:
    return ReferenceStructure(
        object_id="target",
        role="target",
        object_name="target",
        filename="target.cif",
        file_format=region_projection.structure.file_format or "mmcif",
        sha256=region_projection.target_structure_sha256,
        source="stage01-target-bundle",
        created_at=datetime.now(tz=UTC),
    )


def _initial_stage2_pml(
    region_projection: Any,
    current_regions: dict[str, tuple[int, ...]],
) -> str:
    colors = {"A": "red", "B": "blue", "C": "yellow"}
    lines = [
        "# EasyDesign Stage 2 scene",
        f"# @easydesign target object=target sha256={region_projection.target_structure_sha256}",
        "hide everything, all",
        "show cartoon, target",
        "color gray70, target",
    ]
    for region_id in ("A", "B", "C"):
        labels = tuple(current_regions.get(region_id, ()))
        if not labels:
            continue
        selection = f"ed_region_{region_id}"
        lines.extend(
            [
                (
                    f"select {selection}, "
                    f"{_author_selector_from_labels(region_projection.residues, labels)}"
                ),
                f"color {colors[region_id]}, {selection}",
                f"show sticks, {selection}",
            ]
        )
    lines.extend(["orient target", "deselect"])
    return "\n".join(lines) + "\n"


def _scene_objects(session: Any) -> tuple[str, ...]:
    objects = tuple(item.object_name for item in session.reference_structures)
    return objects or ("target",)


def _known_chains(region_projection: Any) -> tuple[str, ...]:
    return tuple(sorted({item.auth_chain_id or "A" for item in region_projection.residues}))


def _assistant_scene_context(
    session: Any,
    region_projection: Any,
    active_version: SceneVersion | None,
) -> dict[str, Any]:
    object_names = _scene_objects(session)
    pml = active_version.pml if active_version is not None else ""
    region_residues = {
        region_id: list(session.current_regions.get(region_id, ()))
        for region_id in ("A", "B", "C")
    }
    residue_numbering = [
        {
            "label_seq_id": item.label_seq_id,
            "auth_chain_id": item.auth_chain_id,
            "auth_residue_id": item.auth_residue_id,
            "insertion_code": item.insertion_code,
        }
        for item in region_projection.residues[:500]
    ]
    chain_rows: dict[str, list[Any]] = {}
    for item in region_projection.residues:
        chain_rows.setdefault(item.auth_chain_id or "A", []).append(item)
    return {
        "stage_number": session.stage_number,
        "structure_metadata": {
            "target_id": region_projection.target_id,
            "target_structure_sha256": session.target_structure_sha256,
            "residue_mapping_sha256": session.residue_mapping_sha256,
            "objects": [
                {
                    "object_name": item.object_name,
                    "role": item.role,
                    "filename": item.filename,
                    "format": item.file_format,
                    "sha256": item.sha256,
                }
                for item in session.reference_structures
            ],
            "chains": [
                {
                    "id": chain_id,
                    "residue_count": len(rows),
                    "auth_start": rows[0].auth_residue_id,
                    "auth_end": rows[-1].auth_residue_id,
                }
                for chain_id, rows in sorted(chain_rows.items())
            ],
            "label_chain_id": "A",
        },
        "numbering": {
            "selection_rule": (
                "界面和未限定的用户数字使用 label_seq_id；只有用户明确说"
                "原始编号/auth/author/PDB 编号时才按 author 编号解释。"
                "ed_region_A/B/C 的 PML 必须使用 EasyDesign 已映射的 author selector"
            ),
            "rows": residue_numbering,
        },
        "current_region_counts": {
            region_id: len(values)
            for region_id, values in region_residues.items()
        },
        "current_regions": region_residues,
        "scene_versions": [
            {
                "version_id": item.version_id,
                "revision": item.revision,
                "actor": item.actor,
                "source": item.source,
                "summary": item.summary,
                "created_at": item.created_at.isoformat(),
            }
            for item in session.scene_versions[-12:]
        ],
        "active_scene_version_id": session.active_scene_version_id,
        "scene": derive_scene_summary(pml, object_names),
        "currentPml": pml,
        "allowed_analysis_methods": ["sasa", "scannet"],
    }


_REGION_SELECTION_NAME = re.compile(r"^ed_region_([ABC])$", re.IGNORECASE)
_REGION_CHAIN_RESI = re.compile(
    r"(?:chain\s+([A-Za-z0-9_.-]+)\s+and\s+)?resi\s+([A-Za-z0-9+\\-]+)",
    re.IGNORECASE,
)


def _reserved_region_commands(pml: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for command in split_pml_commands(pml):
        name, _, remainder = command.partition(" ")
        if name.lower() != "select":
            continue
        selection_name, separator, expression = remainder.partition(",")
        if not separator:
            continue
        match = _REGION_SELECTION_NAME.fullmatch(selection_name.strip())
        if match:
            result[match.group(1).upper()] = expression.strip()
    return result


def _expand_residue_token(token: str) -> tuple[str, ...]:
    if "-" not in token:
        return (token,)
    start, separator, end = token.partition("-")
    if not separator or not start.isdigit() or not end.isdigit():
        return (token,)
    start_value = int(start)
    end_value = int(end)
    if start_value > end_value or end_value - start_value > 10_000:
        raise ConfigurationError(f"无效的残基范围: {token}")
    return tuple(str(value) for value in range(start_value, end_value + 1))


def _regions_from_scene_pml(
    pml: str,
    region_projection: Any,
) -> dict[str, tuple[int, ...]]:
    expressions = _reserved_region_commands(pml)
    known_chains = _known_chains(region_projection)
    lookup: dict[tuple[str, str], int] = {}
    for item in region_projection.residues:
        chain = item.auth_chain_id or "A"
        auth_value = _author_residue_token(
            item.auth_residue_id,
            item.insertion_code,
        )
        key = (chain, auth_value)
        if key in lookup and lookup[key] != item.label_seq_id:
            raise ConfigurationError(
                f"author 编号 {chain}:{auth_value} 不能唯一映射到 label_seq_id"
            )
        lookup[key] = item.label_seq_id
    result: dict[str, tuple[int, ...]] = {}
    for region_id in ("A", "B", "C"):
        expression = expressions.get(region_id)
        if expression is None:
            continue
        if expression.strip().lower() in {"none", "(none)"}:
            continue
        matches = tuple(_REGION_CHAIN_RESI.finditer(expression))
        if not matches:
            raise ConfigurationError(
                f"ed_region_{region_id} 必须使用明确的 chain/resi selector"
            )
        labels: set[int] = set()
        for match in matches:
            chain = match.group(1)
            if chain is None:
                if len(known_chains) != 1:
                    raise ConfigurationError(
                        f"ed_region_{region_id} 在多链结构中必须明确 chain"
                    )
                chain = known_chains[0]
            if chain not in known_chains:
                raise ConfigurationError(f"PML 引用了当前结构中不存在的链: {chain}")
            for raw_token in match.group(2).split("+"):
                for token in _expand_residue_token(raw_token):
                    label = lookup.get((chain, token))
                    if label is None:
                        raise ConfigurationError(
                            f"ed_region_{region_id} 残基 {chain}:{token} "
                            "不能唯一映射到 Target Bundle"
                        )
                    labels.add(label)
        if labels:
            result[region_id] = tuple(sorted(labels))
    return normalize_regions(result)


def _validate_assistant_region_scene(
    pml: str,
    region_projection: Any,
    *,
    current_regions: dict[str, tuple[int, ...]],
    allow_region_changes: bool,
) -> dict[str, tuple[int, ...]]:
    """Derive canonical A/B/C state from the model's complete PML."""

    actual_regions = _regions_from_scene_pml(pml, region_projection)
    if (
        not allow_region_changes
        and actual_regions != normalize_regions(current_regions)
    ):
        raise ConfigurationError(
            "自动寻找区域只能生成 SASA/ScanNet 待确认计划，"
            "模型不能直接改写 A/B/C"
        )
    return actual_regions


def _scientific_analysis_methods(
    message: str,
) -> tuple[Literal["sasa", "scannet"], ...]:
    scientific = re.search(
        r"(?:最佳.*(?:区域|hotspot)|寻找.*(?:区域|hotspot)|预测.*(?:区域|hotspot)|"
        r"自动选区|结合热点|binding\s*site|hotspot|sasa|scannet)",
        message,
        re.IGNORECASE,
    )
    if scientific is None:
        return ()
    methods: list[Literal["sasa", "scannet"]] = []
    if re.search(r"sasa", message, re.IGNORECASE):
        methods.append("sasa")
    if re.search(r"scannet", message, re.IGNORECASE):
        methods.append("scannet")
    return tuple(methods or ["sasa", "scannet"])



_OBJECT_NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,63}$")
_REFERENCE_EXTENSIONS = {".cif": "mmcif", ".mmcif": "mmcif", ".pdb": "pdb", ".ent": "pdb"}


def _safe_reference_format(filename: str) -> str:
    extension = Path(filename).suffix.lower()
    if extension not in _REFERENCE_EXTENSIONS:
        raise ConfigurationError("参考结构只支持 .cif/.mmcif/.pdb/.ent 文件")
    return _REFERENCE_EXTENSIONS[extension]


def _safe_reference_object_name(
    session: Any,
    requested: str | None,
    *,
    fallback: str,
) -> str:
    raw = (requested or fallback).strip()
    raw = re.sub(r"[^A-Za-z0-9_]+", "_", raw).strip("_")
    if not raw or not raw[0].isalpha():
        raw = f"ref_{raw}" if raw else "ref_structure"
    raw = raw[:58]
    if not _OBJECT_NAME_RE.fullmatch(raw):
        raise ConfigurationError("PyMOL 对象名只能包含英文字母、数字和下划线，且必须以字母开头")
    existing = {item.object_name for item in session.reference_structures}
    candidate = raw
    suffix = 2
    while candidate in existing:
        candidate = f"{raw[:55]}_{suffix}"
        suffix += 1
    return candidate


def _reference_root(service: UiServiceState, session: Any) -> Path:
    project_id = str(session.project_id)
    session_id = str(session.session_id)
    project_root = service.project_root(project_id)
    root = (
        project_root
        / "interactive-sessions"
        / session_id
        / "references"
    ).resolve()
    root.relative_to(project_root)
    service.workspace.assert_write_path(root)
    root.mkdir(parents=True, exist_ok=True)
    return root


def _reference_file_path(
    service: UiServiceState,
    session: Any,
    reference: ReferenceStructure,
) -> Path:
    path = (
        _reference_root(service, session)
        / reference.object_id
        / reference.filename
    ).resolve()
    path.relative_to(service.project_root(session.project_id))
    service.workspace.assert_write_path(path)
    return path


def _reference_managed_line(reference: ReferenceStructure) -> str:
    return (
        "# @easydesign reference "
        f"object={reference.object_name} object_id={reference.object_id} "
        f"sha256={reference.sha256}"
    )


def _pml_with_reference(
    active_version: SceneVersion,
    reference: ReferenceStructure,
) -> tuple[str, str]:
    managed = _reference_managed_line(reference)
    addition = "\n".join(
        (
            managed,
            f"show cartoon, {reference.object_name}",
            f"color marine, {reference.object_name}",
            f"orient {reference.object_name}",
        )
    )
    return f"{active_version.pml.rstrip()}\n{addition}\n", managed


def _add_reference_to_scene(
    service: UiServiceState,
    session_id: str,
    *,
    reference: ReferenceStructure,
    source: str,
) -> dict[str, Any]:
    session = service.structure_sessions.load(session_id)
    root = service.registry.resolve(session.run_key)
    region_projection = get_region_editor_projection(
        root,
        run_key=session.run_key,
        signer=service.signer,
    )
    session = service.structure_sessions.ensure_scene(
        session.session_id,
        pml=_initial_stage2_pml(region_projection, session.current_regions),
        target_object=_target_reference(region_projection),
    )
    active = service.structure_sessions.active_scene_version(session.session_id)
    if active is None:
        raise ConfigurationError("结构场景尚未初始化")
    next_pml, managed = _pml_with_reference(active, reference)
    references = tuple(
        item for item in session.reference_structures if item.object_id != reference.object_id
    ) + (reference,)
    known_objects = tuple(sorted(set(_scene_objects(session) + (reference.object_name,))))
    updated, version = service.structure_sessions.save_scene_version(
        session.session_id,
        pml=next_pml,
        actor="system",
        source=source,
        summary=f"添加参考结构 {reference.object_name}",
        base_version_id=session.active_scene_version_id,
        known_object_names=known_objects,
        known_chain_ids=_known_chains(region_projection),
        allowed_new_managed_lines=(managed,),
        reference_structures=references,
    )
    return {
        "session": updated.model_dump(mode="json"),
        "reference": reference.model_dump(mode="json"),
        "version": version.model_dump(mode="json"),
        "result": "reference-added",
    }

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

    @app.get("/api/v1/browser-pymol/status")
    def browser_pymol_status() -> dict[str, Any]:
        root = Path(__file__).resolve().parent / "vendor" / "browser_pymol"
        errors = verify_browser_pymol_assets(root)
        return {
            "available": not errors,
            "integrity_status": "verified" if not errors else "failed",
            "integrity_errors": errors,
            "renderer": "open-source-pymol-wasm",
            "pymol_version": "2.6.0a0",
            "pyodide_version": "0.22.1",
            "offline_assets": True,
        }

    @app.get("/api/v1/structure-assistant/status")
    def assistant_service_status(request: Request) -> dict[str, Any]:
        service = _state(request)
        return service.assistant_providers.platform_status().model_dump(mode="json")

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
            sessions_by_project: dict[str, DesignSession] = {}
            for item in service.sessions.list():
                if not item.config_revisions:
                    continue
                previous = sessions_by_project.get(item.project_id)
                if previous is None or item.updated_at > previous.updated_at:
                    sessions_by_project[item.project_id] = item
            draft_ids = [
                project_id
                for project_id in service.projects()
                if project_id not in project_ids
            ]
            return {
                "projects": [
                    _project_to_dict(
                        get_project_projection(
                            project_id,
                            registry=service.registry,
                            signer=service.signer,
                            accepted_jobs=service.accepted_jobs_by_run(),
                            projects_root=service.projects_root,
                        )
                    )
                    for project_id in project_ids
                ],
                "drafts": [
                    get_project_draft_projection(
                        service.projects_root / project_id,
                        session_id=(
                            None
                            if project_id not in sessions_by_project
                            else sessions_by_project[project_id].session_id
                        ),
                        session_updated_at=(
                            None
                            if project_id not in sessions_by_project
                            else sessions_by_project[project_id].updated_at
                        ),
                    ).model_dump(mode="json")
                    for project_id in draft_ids
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
                accepted_jobs=service.accepted_jobs_by_run(),
                projects_root=service.projects_root,
            )
        except Exception as error:
            _raise_http(error)
            raise

    @app.get("/api/v1/project-preflight")
    def project_preflight(
        request: Request,
        project_id: Annotated[str, Query(min_length=1, max_length=128)],
    ) -> dict[str, Any]:
        try:
            return _state(request).project_preflight(project_id)
        except Exception as error:
            _raise_http(error)
            raise

    @app.get("/api/v1/uploads")
    def uploads(request: Request) -> dict[str, Any]:
        service = _state(request)
        return {
            "receipts": [
                item.model_dump(mode="json")
                for item in service.upload_store.list()
            ],
            "capacity": service.upload_store.capacity(),
            "cleanup_suggestions": [
                item.upload_token
                for item in service.upload_store.suggested_cleanup()
            ],
        }

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
        digest = sha256_bytes(content)
        reusable = service.upload_store.find_reusable(
            filename=filename,
            size_bytes=len(content),
            sha256=digest,
        )
        if reusable is not None:
            service.audit.event(
                "upload.reused",
                operation_id=reusable.upload_token,
                upload_token=reusable.upload_token,
                filename=reusable.filename,
                size_bytes=reusable.size_bytes,
                sha256=reusable.sha256,
                status=reusable.status,
                path=service.workspace.root / reusable.relative_path,
                message="reusing verified pending upload",
            )
            return reusable
        receipt, target = service.upload_store.begin(
            filename=filename,
            size_bytes=len(content),
            sha256=digest,
        )
        service.audit.event(
            "dir.created",
            operation_id=receipt.upload_token,
            upload_token=receipt.upload_token,
            filename=filename,
            size_bytes=len(content),
            sha256=digest,
            path=target.parent,
            message="upload staging directory created",
        )
        try:
            with target.open("xb") as handle:
                handle.write(content)
            ready = service.upload_store.ready(receipt.upload_token)
            service.audit.event(
                "upload.received",
                operation_id=ready.upload_token,
                upload_token=ready.upload_token,
                filename=ready.filename,
                size_bytes=ready.size_bytes,
                sha256=ready.sha256,
                status=ready.status,
                path=target,
                message="browser upload received and verified",
            )
            return ready
        except BaseException as error:
            moved = quarantine_if_workspace_path(
                target.parent,
                operation=receipt.upload_token,
                reason="UI 文件接收未完成",
            )
            if moved is not None:
                service.audit.event(
                    "quarantine.move.done",
                    operation_id=receipt.upload_token,
                    upload_token=receipt.upload_token,
                    filename=filename,
                    from_path=target.parent,
                    to_path=moved,
                    message="UI 文件接收未完成",
                    failure_reason=str(error),
                )
                updated = service.upload_store.relocate(
                    receipt.upload_token,
                    path=moved / target.parent.name / filename,
                    status="failed-quarantined",
                    failure_reason=str(error),
                )
                service.audit.event(
                    "receipt.state.changed",
                    operation_id=updated.upload_token,
                    upload_token=updated.upload_token,
                    filename=updated.filename,
                    status=updated.status,
                    path=service.workspace.root / updated.relative_path,
                    failure_reason=updated.failure_reason,
                )
            raise

    @app.post("/api/v1/uploads/raw")
    async def upload_raw(
        request: Request,
        filename: Annotated[str, Query(min_length=1, max_length=255)],
        sha256: Annotated[str, Query(pattern=r"^[0-9a-f]{64}$")],
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
            if declared_size <= 0:
                raise HTTPException(status_code=400, detail="不能上传空文件")
        if content_length is None:
            raise HTTPException(status_code=411, detail="上传必须提供 Content-Length")
        reusable = service.upload_store.find_reusable(
            filename=safe_filename,
            size_bytes=declared_size,
            sha256=sha256,
        )
        if reusable is not None:
            service.audit.event(
                "upload.reused",
                operation_id=reusable.upload_token,
                upload_token=reusable.upload_token,
                filename=reusable.filename,
                size_bytes=reusable.size_bytes,
                sha256=reusable.sha256,
                status=reusable.status,
                path=service.workspace.root / reusable.relative_path,
                message="reusing verified pending upload",
            )
            return reusable
        receipt, target = service.upload_store.begin(
            filename=safe_filename,
            size_bytes=declared_size,
            sha256=sha256,
        )
        service.audit.event(
            "dir.created",
            operation_id=receipt.upload_token,
            upload_token=receipt.upload_token,
            filename=safe_filename,
            size_bytes=declared_size,
            sha256=sha256,
            path=target.parent,
            message="upload staging directory created",
        )
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
        except BaseException as error:
            moved = quarantine_if_workspace_path(
                target.parent,
                operation=receipt.upload_token,
                reason="UI 文件接收未完成",
            )
            if moved is not None:
                service.audit.event(
                    "quarantine.move.done",
                    operation_id=receipt.upload_token,
                    upload_token=receipt.upload_token,
                    filename=safe_filename,
                    from_path=target.parent,
                    to_path=moved,
                    message="UI 文件接收未完成",
                    failure_reason=str(error),
                )
                updated = service.upload_store.relocate(
                    receipt.upload_token,
                    path=moved / target.parent.name / safe_filename,
                    status="failed-quarantined",
                    failure_reason="UI 文件接收未完成",
                )
                service.audit.event(
                    "receipt.state.changed",
                    operation_id=updated.upload_token,
                    upload_token=updated.upload_token,
                    filename=updated.filename,
                    status=updated.status,
                    path=service.workspace.root / updated.relative_path,
                    failure_reason=updated.failure_reason,
                )
            raise
        if size_bytes != receipt.size_bytes or digest.hexdigest() != receipt.sha256:
            moved = quarantine_if_workspace_path(
                target.parent,
                operation=receipt.upload_token,
                reason="浏览器声明与服务端接收的大小或 SHA-256 不一致",
            )
            if moved is not None:
                service.audit.event(
                    "quarantine.move.done",
                    operation_id=receipt.upload_token,
                    upload_token=receipt.upload_token,
                    filename=safe_filename,
                    from_path=target.parent,
                    to_path=moved,
                    message="浏览器声明与服务端接收的大小或 SHA-256 不一致",
                    failure_reason="上传大小或 SHA-256 不一致",
                )
                updated = service.upload_store.relocate(
                    receipt.upload_token,
                    path=moved / target.parent.name / safe_filename,
                    status="failed-quarantined",
                    failure_reason="上传大小或 SHA-256 不一致",
                )
                service.audit.event(
                    "receipt.state.changed",
                    operation_id=updated.upload_token,
                    upload_token=updated.upload_token,
                    filename=updated.filename,
                    status=updated.status,
                    path=service.workspace.root / updated.relative_path,
                    failure_reason=updated.failure_reason,
                )
            raise HTTPException(status_code=400, detail="上传大小或 SHA-256 不一致")
        ready = service.upload_store.ready(receipt.upload_token)
        service.audit.event(
            "upload.received",
            operation_id=ready.upload_token,
            upload_token=ready.upload_token,
            filename=ready.filename,
            size_bytes=ready.size_bytes,
            sha256=ready.sha256,
            status=ready.status,
            path=target,
            message="browser raw upload received and verified",
        )
        return ready

    @app.post("/api/v1/projects")
    def initialize(payload: ProjectCreateRequest, request: Request) -> dict[str, Any]:
        service = _state(request)
        try:
            if payload.design_mode == "stepwise" and payload.stop_after_stage != 1:
                raise ConfigurationError("按步骤设计首次运行只能停止在 Stage 01")
            if payload.design_mode == "developer-smoke":
                raise ConfigurationError("开发者自检必须使用专用自检接口")
            project_preflight = service.project_preflight(payload.project_id)
            if not project_preflight["available"]:
                suggestion = project_preflight.get("suggested_project_id")
                suffix = f"；建议使用：{suggestion}" if suggestion else ""
                raise ConfigurationError(f"{project_preflight['reason']}{suffix}")
            existing_session = (
                None
                if payload.session_id is None
                else service.sessions.load(payload.session_id)
            )
            if (
                existing_session is not None
                and existing_session.project_id != payload.project_id
            ):
                raise ConfigurationError("产品会话与项目 ID 不一致")
            source_value = payload.source_value
            operation_id = f"create-project-{payload.project_id}"
            staging_root = (
                service.workspace.runtime_root
                / "tmp"
                / f"project-staging-{uuid4().hex}"
            )
            kwargs: dict[str, Any] = {
                "project_root": staging_root,
                "project_id": payload.project_id,
                "target_id": payload.target_id,
                "execution_mode": payload.execution_mode,
                "design_intent": payload.design_intent,
                "stop_after_stage": payload.stop_after_stage,
                "stage06_candidate_count": payload.stage06_candidate_count,
                "stage02_method": payload.stage02_method,
            }
            uploaded_source: Path | None = None
            if payload.source_type == "local-file":
                uploaded_source = service.upload_store.resolve(source_value)
                service.audit.event(
                    "upload.consume.start",
                    operation_id=operation_id,
                    project_id=payload.project_id,
                    upload_token=source_value,
                    filename=uploaded_source.name,
                    path=uploaded_source,
                    message="project creation will move upload into staging inputs",
                )
                kwargs["target"] = uploaded_source
                kwargs["source_transfer"] = "move"
                kwargs["quarantine_on_error"] = False
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
            try:
                outcome = initialize_project(**kwargs)
                service.audit.event(
                    "dir.created",
                    operation_id=operation_id,
                    project_id=payload.project_id,
                    path=staging_root,
                    message="project staging directory created",
                )
                if uploaded_source is not None and outcome.target_path is not None:
                    service.audit.event(
                        "file.move.done",
                        operation_id=operation_id,
                        project_id=payload.project_id,
                        upload_token=source_value,
                        filename=uploaded_source.name,
                        from_path=uploaded_source,
                        to_path=outcome.target_path,
                        message="uploaded target moved into project staging inputs",
                    )
                validated_plan = validate_run_configuration(
                    outcome.config_path,
                    profile_path=service.profile_path,
                    source_base_dir=staging_root,
                )
                now = datetime.now(tz=UTC)
                atomic_dump_runtime_model(
                    ProjectMetadata(
                        project_id=payload.project_id,
                        target_id=validated_plan.target_id,
                        input_type=payload.source_type,
                        design_mode=payload.design_mode,
                        execution_mode=payload.execution_mode,
                        configured_through_stage=(
                            1
                            if payload.design_mode == "stepwise"
                            else payload.stop_after_stage
                        ),
                        config_sha256=sha256_file(outcome.config_path),
                        created_at=now,
                        updated_at=now,
                    ),
                    staging_root / "project-metadata.json",
                )
                destination = service.projects_root / payload.project_id
                if destination.exists():
                    raise ConfigurationError(
                        f"项目名称在发布前已被占用，禁止覆盖: {payload.project_id}"
                    )
                service.audit.event(
                    "file.move.start",
                    operation_id=operation_id,
                    project_id=payload.project_id,
                    from_path=staging_root,
                    to_path=destination,
                    message="publishing project staging directory",
                )
                shutil.move(str(staging_root), str(destination))
                service.audit.event(
                    "project.publish.done",
                    operation_id=operation_id,
                    project_id=payload.project_id,
                    from_path=staging_root,
                    to_path=destination,
                    status="published",
                )
            except Exception as error:
                moved = quarantine_if_workspace_path(
                    staging_root,
                    operation=operation_id,
                    reason="项目创建预检或原子发布失败",
                )
                if moved is not None:
                    service.audit.event(
                        "quarantine.move.done",
                        operation_id=operation_id,
                        project_id=payload.project_id,
                        from_path=staging_root,
                        to_path=moved,
                        message="项目创建预检或原子发布失败",
                        failure_reason=str(error),
                    )
                if uploaded_source is not None:
                    candidate = uploaded_source if uploaded_source.exists() else None
                    status = "failed"
                    if moved is not None:
                        staged_candidate = (
                            moved / staging_root.name / "inputs" / uploaded_source.name
                        )
                        if staged_candidate.is_file():
                            candidate = staged_candidate
                            status = "failed-quarantined"
                    if candidate is not None and candidate.is_file():
                        updated = service.upload_store.relocate(
                            source_value,
                            path=candidate,
                            status=status,
                            failure_reason=str(error),
                        )
                        service.audit.event(
                            "receipt.state.changed",
                            operation_id=operation_id,
                            project_id=payload.project_id,
                            upload_token=source_value,
                            filename=updated.filename,
                            status=updated.status,
                            path=service.workspace.root / updated.relative_path,
                            failure_reason=updated.failure_reason,
                        )
                raise
            published_config = destination / "easydesign.yaml"
            session = existing_session or service.sessions.create(
                project_id=payload.project_id,
                design_mode=payload.design_mode,
                execution_mode=payload.execution_mode,
            )
            session = service.sessions.add_config_revision(
                session.session_id,
                stage_number=1 if payload.design_mode == "stepwise" else payload.stop_after_stage,
                config_path=published_config,
            )
            if uploaded_source is not None:
                published_input = destination / "inputs" / uploaded_source.name
                updated = service.upload_store.relocate(
                    source_value,
                    path=published_input,
                    status="published",
                    project_id=payload.project_id,
                )
                service.audit.event(
                    "receipt.state.changed",
                    operation_id=operation_id,
                    project_id=payload.project_id,
                    upload_token=source_value,
                    filename=updated.filename,
                    status=updated.status,
                    path=published_input,
                )
            return {
                "project_id": payload.project_id,
                "config": published_config.read_text(encoding="utf-8"),
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
            service.assert_project_is_draft(project_id)
            project_root = service.project_root(project_id)
            operation_id = f"config-validation-{uuid4().hex}"
            temporary = service.temporary_root / f"{operation_id}.yaml"
            with temporary.open("x", encoding="utf-8") as handle:
                handle.write(payload.yaml_text)
            service.audit.event(
                "config.validation.staged",
                operation_id=operation_id,
                project_id=project_id,
                path=temporary,
                message="temporary config staged for validation",
            )
            try:
                plan = validate_run_configuration(
                    temporary,
                    profile_path=service.profile_path,
                    runs_root=service.registry.runs_root,
                    source_base_dir=project_root,
                )
            finally:
                moved = quarantine_if_workspace_path(
                    temporary,
                    operation=operation_id,
                    reason="UI 配置校验 staging 已终止",
                )
                if moved is not None:
                    service.audit.event(
                        "quarantine.move.done",
                        operation_id=operation_id,
                        project_id=project_id,
                        from_path=temporary,
                        to_path=moved,
                        message="UI 配置校验 staging 已终止",
                    )
            published = service.publish_project_config(project_id, payload.yaml_text)
            metadata_path = service.projects_root / project_id / "project-metadata.json"
            if metadata_path.is_file():
                metadata = load_latest_runtime_model(metadata_path, ProjectMetadata)
                atomic_dump_runtime_model(
                    metadata.model_copy(
                        update={
                            "configured_through_stage": plan.stop_after_stage,
                            "config_sha256": sha256_file(published),
                            "updated_at": datetime.now(tz=UTC),
                        }
                    ),
                    metadata_path,
                )
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
            project_root = service.project_root(payload.project_id)
            plan = validate_run_configuration(
                config,
                profile_path=service.profile_path,
                runs_root=service.registry.runs_root,
                source_base_dir=project_root,
            )
            if payload.executor_id is None:
                diagnostic: Any = diagnose_runtime(
                    profile_path=service.profile_path,
                    config_path=config,
                    runs_root=service.registry.runs_root,
                    source_base_dir=project_root,
                )
            else:
                pairing = RemoteExecutorRegistry(service.workspace).latest(
                    payload.executor_id
                )
                remote_probe = (
                    probe_managed_executor(
                        executor_id=payload.executor_id,
                        profile_path=service.profile_path,
                    )
                    if pairing is not None and pairing.state == "paired"
                    else probe_remote_executor(
                        executor_id=payload.executor_id,
                        profile_path=service.profile_path,
                    )
                )
                diagnostic = {
                    "status": "remote-reachable",
                    "executor_id": payload.executor_id,
                    "execution_target": (
                        "managed-ssh"
                        if pairing is not None and pairing.state == "paired"
                        else "legacy-ssh"
                    ),
                    "probe": remote_probe.model_dump(mode="json"),
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
            service.assert_project_is_draft(payload.project_id)
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
                pairing = RemoteExecutorRegistry(service.workspace).latest(
                    payload.executor_id
                )
                if pairing is not None and pairing.state == "paired":
                    raise ConfigurationError(
                        "Suzhou2 受管队列只在 Stage 04/06 配置页接受"
                        "已完成 Stage 03/05 的 continuation；Stage 01–03 在当前机器执行。"
                    )
                run_id = payload.run_id or f"remote-{uuid4().hex[:16]}"
                config_path = service.project_config(payload.project_id)
                project_root = service.project_root(payload.project_id)
                submission = submit_remote_pipeline(
                    executor_id=payload.executor_id,
                    job_id=f"ui-{uuid4().hex[:16]}",
                    run_id=run_id,
                    config_path=config_path,
                    project_root=project_root,
                    profile_path=service.profile_path,
                )
                accepted = service.jobs.accept_external(
                    operation="remote-run",
                    project_id=payload.project_id,
                    stage_number=payload.stage_number or 1,
                    external_job_id=submission.job_id,
                    run_id=submission.run_id,
                    session_id=payload.session_id,
                    status=submission.status,
                )
                return {
                    "kind": "remote",
                    "executor_id": submission.executor_id,
                    "job_id": submission.job_id,
                    "project_id": submission.project_id,
                    "run_id": submission.run_id,
                    "submitted_at": submission.submitted_at.isoformat(),
                    "status": submission.status,
                    "acceptance_job_id": accepted.job_id,
                }
            return service.jobs.launch(
                operation="run",
                config_path=service.project_config(payload.project_id),
                profile_path=service.profile_path,
                runs_root=service.registry.runs_root,
                run_id=payload.run_id,
                project_id=payload.project_id,
                session_id=payload.session_id,
                session_root=(
                    None if payload.session_id is None else service.sessions.root
                ),
                stage_number=payload.stage_number or 1,
                confirmed=payload.confirmed,
            )
        except Exception as error:
            _raise_http(error)
            raise

    @app.get("/api/v1/execution-targets")
    def execution_targets(request: Request) -> dict[str, Any]:
        """Project local GPU readiness and registered managed destinations."""

        service = _state(request)
        local: dict[str, Any]
        try:
            snapshots = NvidiaSmiProbe().snapshots()
            inventory = GpuLeaseStore(context=service.workspace).inventory(
                snapshots,
                target=LocalCurrentHostTarget(),
                max_memory_used_mib=1024,
                max_utilization_percent=10,
            )
            local = {
                "type": "local-current-host",
                "status": "available" if inventory.selected_devices else "waiting-resource",
                "gpu_count": len(inventory.devices),
                "eligible_gpu_count": len(inventory.selected_devices),
                "selected_devices": list(inventory.selected_devices),
                "devices": [item.model_dump(mode="json") for item in inventory.devices],
                "detail": (
                    "当前有可用 GPU"
                    if inventory.selected_devices
                    else "当前无符合条件的 GPU，提交后将等待资源"
                ),
            }
        except Exception as error:
            local = {
                "type": "local-current-host",
                "status": "unavailable",
                "gpu_count": 0,
                "eligible_gpu_count": 0,
                "selected_devices": [],
                "devices": [],
                "detail": str(error)[:4096] or type(error).__name__,
            }
        pairings = RemoteExecutorRegistry(service.workspace).list_latest()
        managed: list[dict[str, Any]] = []
        for record in pairings:
            projection: dict[str, Any] = {
                **_pairing_projection(record),
                "type": "managed-ssh",
                "label": (
                    "Suzhou2 公共算力"
                    if record.executor_id == "suzhou2"
                    else record.executor_id
                ),
                "status": "unavailable",
                "gpu_count": 0,
                "eligible_gpu_count": 0,
                "devices": [],
                "queue_depth": 0,
                "running_jobs": 0,
                "resource_observed_at": None,
                "detail": "完成配对后可读取受管 GPU 状态",
            }
            if record.state == "paired":
                try:
                    probe = probe_managed_executor(
                        executor_id=record.executor_id,
                        profile_path=service.profile_path,
                        # A managed probe also verifies the fixed scientific
                        # backends. Under an active 8-GPU run this takes about
                        # 35 seconds; the UI keeps selection usable while it
                        # loads, so allow the truthful snapshot to complete.
                        timeout_seconds=60.0,
                    )
                except Exception:
                    projection["detail"] = (
                        "已配对，但暂时无法读取受管 GPU 状态；"
                        "可稍后刷新，或先选择当前机器"
                    )
                else:
                    projection.update(
                        {
                            "status": (
                                "available"
                                if probe.eligible_gpu_count
                                else "waiting-resource"
                            ),
                            "gpu_count": probe.gpu_count,
                            "eligible_gpu_count": probe.eligible_gpu_count,
                            "devices": [
                                item.model_dump(mode="json")
                                for item in probe.gpu_devices
                            ],
                            "queue_depth": probe.queue_depth,
                            "running_jobs": probe.running_jobs,
                            "resource_observed_at": probe.observed_at.isoformat(),
                            "detail": (
                                f"当前 {probe.eligible_gpu_count}/{probe.gpu_count} "
                                "张 GPU 符合启动条件"
                                if probe.eligible_gpu_count
                                else "当前没有空闲 GPU；任务仍可进入统一队列等待"
                            ),
                        }
                    )
            managed.append(projection)
        return {
            "local": local,
            "managed": managed,
        }

    @app.get("/api/v1/remote-executors")
    def remote_executors(request: Request) -> dict[str, Any]:
        service = _state(request)
        try:
            registry = RemoteExecutorRegistry(service.workspace)
            pairings = {
                item.executor_id: item
                for item in registry.list_latest()
            }
            executor_ids = set(
                list_remote_executor_ids(profile_path=service.profile_path)
            ) | set(pairings)
            # Suzhou2 is a first-class managed destination even before the
            # controller has started pairing it.
            executor_ids.add("suzhou2")
            return {
                "executors": [
                    {
                        "executor_id": executor_id,
                        "label": (
                            "Suzhou2 公共算力"
                            if executor_id == "suzhou2"
                            else executor_id
                        ),
                        "type": (
                            "managed-ssh"
                            if executor_id == "suzhou2" or executor_id in pairings
                            else "legacy-ssh"
                        ),
                        "pairing_state": (
                            "not-paired"
                            if executor_id not in pairings
                            else pairings[executor_id].state
                        ),
                        "controller_id": (
                            None
                            if executor_id not in pairings
                            else pairings[executor_id].controller_id
                        ),
                        "host": None if executor_id not in pairings else pairings[executor_id].host,
                        "port": None if executor_id not in pairings else pairings[executor_id].port,
                        "user": None if executor_id not in pairings else pairings[executor_id].user,
                        "host_fingerprint": (
                            None
                            if executor_id not in pairings
                            else pairings[executor_id].host_identity.fingerprint
                        ),
                        "key_pair_available": registry.key_pair_available(executor_id),
                    }
                    for executor_id in sorted(executor_ids)
                ]
            }
        except Exception as error:
            _raise_http(error)
            raise

    @app.post("/api/v1/remote-executors/host-scan")
    def remote_host_scan(payload: RemoteHostScanRequest) -> dict[str, Any]:
        try:
            return scan_host_identity(
                host=payload.host, port=payload.port
            ).model_dump(mode="json")
        except Exception as error:
            _raise_http(error)
            raise

    @app.post("/api/v1/remote-executors/pair-begin")
    def remote_pair_begin(
        payload: RemotePairBeginRequest, request: Request
    ) -> dict[str, Any]:
        service = _state(request)
        try:
            registry = RemoteExecutorRegistry(service.workspace)
            key_pair_reused = registry.key_pair_available(payload.executor_id)
            record = registry.begin_pairing(
                executor_id=payload.executor_id,
                controller_id=payload.controller_id,
                host=payload.host,
                port=payload.port,
                user=payload.user,
                confirmed_host_fingerprint=payload.confirmed_host_fingerprint,
            )
            return {
                "pairing": _pairing_projection(record, include_public_key=True),
                "public_key_install_command": public_key_install_command(record),
                "key_pair_reused": key_pair_reused,
            }
        except Exception as error:
            _raise_http(error)
            raise

    @app.post("/api/v1/remote-executors/{executor_id}/pair-password-bootstrap")
    def remote_pair_password_bootstrap(
        executor_id: str,
        payload: RemotePairPasswordRequest,
        request: Request,
    ) -> dict[str, Any]:
        service = _state(request)
        try:
            if not payload.confirmed:
                raise ConfigurationError("一次性密码安装必须明确 confirmed=true")
            registry = RemoteExecutorRegistry(service.workspace)
            waiting = registry.latest(executor_id)
            if waiting is None or waiting.state != "awaiting-public-key":
                raise ConfigurationError("executor 不处于等待公钥安装状态")
            installation = install_public_key_with_password(
                waiting,
                payload.password.get_secret_value(),
            )
            try:
                probe = probe_pending_managed_executor(waiting)
            except Exception as probe_error:
                return {
                    "status": "key-installed-worker-not-ready",
                    "pairing": _pairing_projection(waiting),
                    "installation": installation.model_dump(mode="json"),
                    "probe_error": str(probe_error),
                }
            paired = registry.mark_paired(executor_id)
            return {
                "status": "paired",
                "pairing": _pairing_projection(paired),
                "installation": installation.model_dump(mode="json"),
                "probe": probe.model_dump(mode="json"),
            }
        except Exception as error:
            _raise_http(error)
            raise

    @app.post("/api/v1/remote-executors/{executor_id}/pair-confirm")
    def remote_pair_confirm(
        executor_id: str,
        payload: RemotePairActionRequest,
        request: Request,
    ) -> dict[str, Any]:
        service = _state(request)
        try:
            if not payload.confirmed:
                raise ConfigurationError("完成配对必须明确 confirmed=true")
            registry = RemoteExecutorRegistry(service.workspace)
            waiting = registry.latest(executor_id)
            if waiting is None or waiting.state != "awaiting-public-key":
                raise ConfigurationError("executor 不处于等待公钥安装状态")
            probe = probe_pending_managed_executor(waiting)
            paired = registry.mark_paired(executor_id)
            return {
                "pairing": _pairing_projection(paired),
                "probe": probe.model_dump(mode="json"),
            }
        except Exception as error:
            _raise_http(error)
            raise

    @app.post("/api/v1/remote-executors/{executor_id}/unpair")
    def remote_unpair(
        executor_id: str,
        payload: RemotePairActionRequest,
        request: Request,
    ) -> dict[str, Any]:
        service = _state(request)
        try:
            if not payload.confirmed:
                raise ConfigurationError("逻辑解绑必须明确 confirmed=true")
            record = RemoteExecutorRegistry(service.workspace).unpair(executor_id)
            return {
                "status": "unpaired",
                "pairing": _pairing_projection(record),
                "preserved": ["控制端私钥", "远端公钥", "历史运行证据"],
            }
        except Exception as error:
            _raise_http(error)
            raise

    @app.get("/api/v1/remote-jobs")
    def remote_jobs() -> dict[str, Any]:
        legacy_jobs = [
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
        managed_jobs = [
            {
                "executor_id": record.executor_id,
                "job_id": record.job_id,
                "project_id": record.project_id,
                "run_id": record.run_id,
                "submitted_at": record.submitted_at.isoformat(),
                "stage_range": list(record.stage_range),
                "candidate_budget": record.candidate_budget,
                "queue_status": record.queue_status,
                "kind": "managed-ssh",
            }
            for record in list_managed_remote_submissions()
        ]
        return {"jobs": [*legacy_jobs, *managed_jobs]}

    @app.get("/api/v1/remote-jobs/{executor_id}/{job_id}")
    def remote_job(executor_id: str, job_id: str, request: Request) -> dict[str, Any]:
        service = _state(request)
        try:
            if any(
                item.job_id == job_id
                for item in list_managed_remote_submissions(executor_id=executor_id)
            ):
                managed = observe_managed_pipeline(
                    executor_id=executor_id,
                    job_id=job_id,
                    profile_path=service.profile_path,
                )
                return managed.model_dump(mode="json")
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
            if any(
                item.job_id == job_id
                for item in list_managed_remote_submissions(executor_id=executor_id)
            ):
                observation = observe_managed_pipeline(
                    executor_id=executor_id,
                    job_id=job_id,
                    profile_path=service.profile_path,
                )
                return {
                    "executor_id": executor_id,
                    "job_id": job_id,
                    "status": (
                        "temporarily-disconnected"
                        if observation.queue is None
                        else observation.queue.status
                    ),
                    "message": (
                        "受管 worker 依据队列 attempt 和 heartbeat 自动恢复；"
                        "不创建额外 shell worker。"
                    ),
                }
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
            managed_record = next(
                (
                    item
                    for item in list_managed_remote_submissions(
                        executor_id=executor_id
                    )
                    if item.job_id == job_id
                ),
                None,
            )
            if record is None and managed_record is None:
                raise ConfigurationError("远程任务记录不存在")
            project_id = (
                record.submission.project_id
                if record is not None
                else managed_record.project_id  # type: ignore[union-attr]
            )
            run_id = (
                record.submission.run_id
                if record is not None
                else managed_record.run_id  # type: ignore[union-attr]
            )
            destination = (
                service.registry.runs_root
                / project_id
                / run_id
            )
            report = sync_remote_pipeline(
                executor_id=executor_id,
                job_id=job_id,
                destination=destination,
                mode=payload.mode,
                profile_path=service.profile_path,
            )
            service.discover_runs()
            run_key = service.registry.register(destination)
            return {
                "status": "synced",
                "executor_id": executor_id,
                "job_id": job_id,
                "mode": report.mode,
                "file_count": report.file_count,
                "size_bytes": report.size_bytes,
                "run_manifest_sha256": report.run_manifest_sha256,
                "run_key": run_key,
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
            accepted_stage, accepted_at, accepted_status = (
                service.accepted_job_for_run(run_key)
            )
            return get_run_projection(
                service.registry.resolve(run_key),
                registry=service.registry,
                signer=service.signer,
                accepted_job_stage=accepted_stage,
                accepted_job_at=accepted_at,
                accepted_job_status=accepted_status,
                projects_root=service.projects_root,
            )
        except Exception as error:
            _raise_http(error)
            raise

    @app.post("/api/v1/runs/{run_key}/structure-sessions")
    def create_structure_session(
        run_key: str,
        payload: StructureSessionCreateRequest,
        request: Request,
    ) -> Any:
        service = _state(request)
        try:
            root = service.registry.resolve(run_key)
            run_projection = get_run_projection(
                root,
                registry=service.registry,
                signer=service.signer,
                projects_root=service.projects_root,
            )
            region_projection = get_region_editor_projection(
                root,
                run_key=run_key,
                signer=service.signer,
            )
            current_regions: dict[str, tuple[int, ...]] = {}
            for region_id in ("A", "B", "C"):
                current_regions[region_id] = tuple(
                    item.label_seq_id
                    for item in region_projection.residues
                    if item.current_region == region_id
                )
            session = service.structure_sessions.get_or_create(
                project_id=run_projection.project_id,
                run_key=run_key,
                stage_number=payload.stage_number,
                target_structure_sha256=(
                    region_projection.target_structure_sha256
                ),
                residue_mapping_sha256=(
                    region_projection.residue_mapping_sha256
                ),
                current_regions=current_regions,
            )
            return service.structure_sessions.ensure_scene(
                session.session_id,
                pml=_initial_stage2_pml(region_projection, current_regions),
                target_object=_target_reference(region_projection),
            )
        except Exception as error:
            _raise_http(error)
            raise

    @app.get("/api/v1/structure-sessions/{session_id}")
    def structure_session(session_id: str, request: Request) -> Any:
        service = _state(request)
        try:
            return service.structure_sessions.load(session_id)
        except Exception as error:
            _raise_http(error)
            raise

    @app.post("/api/v1/structure-sessions/{session_id}/scene-versions/{version_id}/restore")
    def restore_structure_scene_version(
        session_id: str,
        version_id: str,
        payload: SceneVersionRestoreRequest,
        request: Request,
    ) -> Any:
        service = _state(request)
        try:
            if not payload.confirmed:
                raise ConfigurationError("恢复 PML 场景版本必须明确 confirmed=true")
            session = service.structure_sessions.load(session_id)
            target_version = next(
                (
                    item
                    for item in session.scene_versions
                    if item.version_id == version_id
                ),
                None,
            )
            if target_version is None:
                raise ConfigurationError("要恢复的 PML 场景版本不存在")
            current_regions = session.current_regions
            if session.stage_number == 2:
                root = service.registry.resolve(session.run_key)
                region_projection = get_region_editor_projection(
                    root,
                    run_key=session.run_key,
                    signer=service.signer,
                )
                current_regions = _regions_from_scene_pml(
                    target_version.pml,
                    region_projection,
                )
            updated, version = service.structure_sessions.restore_scene_version(
                session_id,
                version_id=version_id,
                base_version_id=payload.base_version_id,
                current_regions=current_regions,
            )
            return {
                "session": updated.model_dump(mode="json"),
                "version": version.model_dump(mode="json"),
                "result": "scene-version-restored",
            }
        except Exception as error:
            _raise_http(error)
            raise

    @app.post("/api/v1/structure-sessions/{session_id}/messages")
    def structure_assistant_message(
        session_id: str,
        payload: AssistantMessageRequest,
        request: Request,
    ) -> Any:
        service = _state(request)
        try:
            session = service.structure_sessions.load(session_id)
            root = service.registry.resolve(session.run_key)
            region_projection = get_region_editor_projection(
                root,
                run_key=session.run_key,
                signer=service.signer,
            )
            if (
                region_projection.target_structure_sha256
                != session.target_structure_sha256
                or region_projection.residue_mapping_sha256
                != session.residue_mapping_sha256
            ):
                raise ConfigurationError(
                    "交互会话的结构或编号映射已与来源运行不一致"
                )
            session = service.structure_sessions.ensure_scene(
                session.session_id,
                pml=_initial_stage2_pml(region_projection, session.current_regions),
                target_object=_target_reference(region_projection),
            )
            active_version = service.structure_sessions.active_scene_version(session_id)
            object_names = _scene_objects(session)
            chain_ids = _known_chains(region_projection)
            secret = service.assistant_providers.load_platform()
            analysis_methods = (
                _scientific_analysis_methods(payload.message)
                if session.stage_number == 2
                else ()
            )
            scene_context = _assistant_scene_context(
                session,
                region_projection,
                active_version,
            )
            if analysis_methods:
                scene_context["scientific_analysis_request"] = {
                    "methods": list(analysis_methods),
                    "requires_confirmation": True,
                }
            next_regions = session.current_regions

            def validate_stage2_scene(edit: ChatPyMolEdit) -> ChatPyMolEdit:
                nonlocal next_regions
                if session.stage_number != 2:
                    return edit
                next_regions = _validate_assistant_region_scene(
                    edit.pml,
                    region_projection,
                    current_regions=session.current_regions,
                    allow_region_changes=not bool(analysis_methods),
                )
                return edit

            edit, request_id, skill_ids = request_assistant_pml_edit(
                secret=secret,
                user_text=payload.message,
                context=scene_context,
                history=session.messages,
                previous_pml="" if active_version is None else active_version.pml,
                known_object_names=object_names,
                known_chain_ids=chain_ids,
                edit_validator=validate_stage2_scene,
            )
            if analysis_methods:
                proposal = AssistantProposal(
                    kind="analysis-plan",
                    explanation=edit.assistant_message,
                    analysis_plan=ScientificAnalysisPlan(
                        methods=analysis_methods,
                        requires_confirmation=True,
                        reason=edit.summary,
                    ),
                )
                return service.structure_sessions.append_chatpymol_exchange(
                    session_id,
                    user_text=payload.message,
                    edit=edit,
                    skill_ids=skill_ids,
                    proposal=proposal,
                    provider=secret.provider,
                    model=secret.model,
                    request_id=request_id,
                    known_object_names=object_names,
                    known_chain_ids=chain_ids,
                    current_regions=session.current_regions,
                )
            return service.structure_sessions.append_chatpymol_exchange(
                session_id,
                user_text=payload.message,
                edit=edit,
                provider=secret.provider,
                model=secret.model,
                request_id=request_id,
                skill_ids=skill_ids,
                known_object_names=object_names,
                known_chain_ids=chain_ids,
                current_regions=next_regions,
            )
        except Exception as error:
            _raise_http(error)
            raise

    @app.put("/api/v1/structure-sessions/{session_id}/scene-pml")
    def save_structure_scene_pml(
        session_id: str,
        payload: PmlRequest,
        request: Request,
    ) -> Any:
        service = _state(request)
        try:
            session = service.structure_sessions.load(session_id)
            root = service.registry.resolve(session.run_key)
            region_projection = get_region_editor_projection(
                root,
                run_key=session.run_key,
                signer=service.signer,
            )
            active = service.structure_sessions.active_scene_version(session_id)
            current_regions = session.current_regions
            if (
                session.stage_number == 2
                and active is not None
                and _reserved_region_commands(payload.pml)
                != _reserved_region_commands(active.pml)
            ):
                current_regions = _regions_from_scene_pml(payload.pml, region_projection)
            updated, version = service.structure_sessions.save_scene_version(
                session_id,
                pml=payload.pml,
                actor="human" if payload.source == "expert-console" else "viewer",
                source=f"pml-editor:{payload.source}",
                summary="人工编辑完整 PML 场景",
                base_version_id=(
                    payload.base_version_id
                    if payload.base_version_id is not None
                    else session.active_scene_version_id
                ),
                known_object_names=_scene_objects(session),
                known_chain_ids=_known_chains(region_projection),
                current_regions=current_regions,
            )
            return {
                "session": updated.model_dump(mode="json"),
                "version": version.model_dump(mode="json"),
                "result": "scene-pml-saved",
            }
        except Exception as error:
            _raise_http(error)
            raise



    @app.post("/api/v1/structure-sessions/{session_id}/references/uploads")
    def add_uploaded_structure_reference(
        session_id: str,
        payload: ReferenceUploadRequest,
        request: Request,
    ) -> Any:
        service = _state(request)
        try:
            if not payload.confirmed:
                raise ConfigurationError("添加参考结构必须明确 confirmed=true")
            session = service.structure_sessions.load(session_id)
            source = service.upload_store.resolve(payload.upload_token)
            filename = _safe_filename(source.name)
            file_format = _safe_reference_format(filename)
            object_name = _safe_reference_object_name(
                session,
                payload.object_name,
                fallback=f"ref_{Path(filename).stem}",
            )
            object_id = f"reference-{uuid4().hex[:12]}"
            destination_dir = _reference_root(service, session) / object_id
            destination_dir.mkdir(parents=True, exist_ok=False)
            destination = destination_dir / filename
            service.audit.event(
                "dir.created",
                operation_id=object_id,
                project_id=session.project_id,
                path=destination_dir,
                message="structure reference directory created",
            )
            shutil.move(str(source), str(destination))
            digest = sha256_file(destination)
            receipt = service.upload_store.load(payload.upload_token)
            if digest != receipt.sha256:
                raise ConfigurationError("参考结构上传文件 SHA-256 复核失败")
            service.upload_store.relocate(
                payload.upload_token,
                path=destination,
                status="published",
                project_id=session.project_id,
            )
            service.audit.event(
                "reference.upload.published",
                operation_id=object_id,
                upload_token=payload.upload_token,
                project_id=session.project_id,
                filename=filename,
                sha256=digest,
                from_path=source,
                to_path=destination,
                status="published",
            )
            reference = ReferenceStructure(
                object_id=object_id,
                role="reference",
                object_name=object_name,
                filename=filename,
                file_format=file_format,
                sha256=digest,
                source=f"upload:{payload.upload_token}",
                created_at=datetime.now(tz=UTC),
            )
            return _add_reference_to_scene(
                service,
                session_id,
                reference=reference,
                source="reference-upload",
            )
        except Exception as error:
            _raise_http(error)
            raise

    @app.post("/api/v1/structure-sessions/{session_id}/references/rcsb")
    def add_rcsb_structure_reference(
        session_id: str,
        payload: ReferenceRcsbRequest,
        request: Request,
    ) -> Any:
        service = _state(request)
        try:
            if not payload.confirmed:
                raise ConfigurationError("拉取 RCSB 参考结构必须明确 confirmed=true")
            session = service.structure_sessions.load(session_id)
            rcsb_id = payload.rcsb_id.upper()
            filename = f"{rcsb_id}.cif"
            object_name = _safe_reference_object_name(
                session,
                payload.object_name,
                fallback=f"ref_{rcsb_id.lower()}",
            )
            object_id = f"reference-{uuid4().hex[:12]}"
            destination_dir = _reference_root(service, session) / object_id
            destination_dir.mkdir(parents=True, exist_ok=False)
            destination = destination_dir / filename
            url = f"https://files.rcsb.org/download/{rcsb_id}.cif"
            with httpx.Client(
                timeout=httpx.Timeout(60.0, connect=10.0, read=45.0),
                trust_env=False,
            ) as client:
                response = client.get(url)
                if response.status_code == 404:
                    raise ConfigurationError(f"RCSB 没有找到结构 {rcsb_id}")
                response.raise_for_status()
                content = response.content
            if not content:
                raise ConfigurationError("RCSB 返回了空结构文件")
            if len(content) > MAX_UPLOAD_BYTES:
                raise ConfigurationError("RCSB 参考结构超过 64 MiB 上限")
            destination.write_bytes(content)
            digest = sha256_bytes(content)
            service.audit.event(
                "reference.rcsb.downloaded",
                operation_id=object_id,
                project_id=session.project_id,
                filename=filename,
                sha256=digest,
                to_path=destination,
                source_url=url,
                status="published",
            )
            reference = ReferenceStructure(
                object_id=object_id,
                role="reference",
                object_name=object_name,
                filename=filename,
                file_format="mmcif",
                sha256=digest,
                source=f"rcsb:{rcsb_id}",
                created_at=datetime.now(tz=UTC),
            )
            return _add_reference_to_scene(
                service,
                session_id,
                reference=reference,
                source="reference-rcsb",
            )
        except Exception as error:
            _raise_http(error)
            raise

    @app.get("/api/v1/structure-sessions/{session_id}/references/{object_id}/file")
    def structure_reference_file(
        session_id: str,
        object_id: str,
        request: Request,
        download: bool = False,
    ) -> FileResponse:
        service = _state(request)
        try:
            session = service.structure_sessions.load(session_id)
            reference = next(
                (
                    item for item in session.reference_structures
                    if item.object_id == object_id and item.role == "reference"
                ),
                None,
            )
            if reference is None:
                raise ConfigurationError("参考结构不存在")
            path = _reference_file_path(service, session, reference)
            if not path.is_file():
                raise ConfigurationError("参考结构文件不存在")
            if sha256_file(path) != reference.sha256:
                raise ConfigurationError("参考结构文件 SHA-256 与记录不一致")
            media_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
            return FileResponse(
                path,
                media_type=media_type,
                filename=reference.filename if download else None,
            )
        except Exception as error:
            _raise_http(error)
            raise

    @app.post("/api/v1/structure-sessions/{session_id}/pml")
    def append_structure_pml(
        session_id: str,
        payload: PmlRequest,
        request: Request,
    ) -> Any:
        service = _state(request)
        try:
            return service.structure_sessions.append_pml(
                session_id,
                pml=payload.pml,
                source=payload.source,
            )
        except Exception as error:
            _raise_http(error)
            raise

    @app.post(
        "/api/v1/structure-sessions/{session_id}/proposals/"
        "{proposal_id}/apply"
    )
    def apply_structure_proposal(
        session_id: str,
        proposal_id: str,
        payload: ProposalApplyRequest,
        request: Request,
    ) -> Any:
        service = _state(request)
        try:
            if not payload.confirmed:
                raise ConfigurationError("应用助手建议必须明确 confirmed=true")
            session = service.structure_sessions.load(session_id)
            proposal = service.structure_sessions.proposal(
                session_id,
                proposal_id,
            )
            if proposal.kind == "pml-edit" and proposal.pml_edit is not None:
                root = service.registry.resolve(session.run_key)
                region_projection = get_region_editor_projection(
                    root,
                    run_key=session.run_key,
                    signer=service.signer,
                )
                updated, version = service.structure_sessions.save_scene_version(
                    session_id,
                    pml=proposal.pml_edit.pml,
                    actor="ai",
                    source="assistant-proposal",
                    summary=proposal.pml_edit.summary,
                    base_version_id=session.active_scene_version_id,
                    known_object_names=_scene_objects(session),
                    known_chain_ids=_known_chains(region_projection),
                )
                return {
                    "session": updated.model_dump(mode="json"),
                    "result": "pml-edit-applied",
                    "version": version.model_dump(mode="json"),
                }
            if proposal.kind == "view-control" and proposal.view_control is not None:
                if (
                    proposal.view_control.action == "undo-last-view-action"
                    and len(session.scene_versions) >= 2
                ):
                    previous = session.scene_versions[-2]
                    updated, version = service.structure_sessions.restore_scene_version(
                        session_id,
                        version_id=previous.version_id,
                        base_version_id=session.active_scene_version_id,
                    )
                    return {
                        "session": updated.model_dump(mode="json"),
                        "result": "scene-version-restored",
                        "version": version.model_dump(mode="json"),
                    }
                if proposal.view_control.action == "reset-default-view" and session.scene_versions:
                    first = session.scene_versions[0]
                    updated, version = service.structure_sessions.restore_scene_version(
                        session_id,
                        version_id=first.version_id,
                        base_version_id=session.active_scene_version_id,
                    )
                    return {
                        "session": updated.model_dump(mode="json"),
                        "result": "scene-version-restored",
                        "version": version.model_dump(mode="json"),
                    }
            if proposal.kind == "viewer-actions":
                updated = service.structure_sessions.apply_proposal(
                    session_id,
                    proposal_id=proposal_id,
                    viewer_actions=proposal.viewer_actions,
                    source="assistant",
                )
                return {
                    "session": updated.model_dump(mode="json"),
                    "result": "viewer-actions-applied",
                }
            if proposal.kind == "region-edit":
                root = service.registry.resolve(session.run_key)
                service.assert_stage_configurable(session.run_key, 2)
                region_projection = get_region_editor_projection(
                    root,
                    run_key=session.run_key,
                    signer=service.signer,
                )
                if (
                    region_projection.target_structure_sha256
                    != session.target_structure_sha256
                    or region_projection.residue_mapping_sha256
                    != session.residue_mapping_sha256
                ):
                    raise ConfigurationError(
                        "应用区域建议前，结构或编号映射校验失败"
                    )
                updated_regions = _apply_region_operations(
                    session.current_regions,
                    proposal.region_operations,
                    region_projection.residues,
                )
                updated = service.structure_sessions.apply_proposal(
                    session_id,
                    proposal_id=proposal_id,
                    current_regions=updated_regions,
                )
                return {
                    "session": updated.model_dump(mode="json"),
                    "result": "region-edit-applied-to-draft",
                }
            if proposal.kind == "analysis-plan":
                service.assert_stage_configurable(session.run_key, 2)
                return {
                    "session": session.model_dump(mode="json"),
                    "result": "analysis-plan-confirmed",
                    "analysis_plan": (
                        None
                        if proposal.analysis_plan is None
                        else proposal.analysis_plan.model_dump(mode="json")
                    ),
                }
            return {
                "session": session.model_dump(mode="json"),
                "result": "explanation-has-no-action",
            }
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
            accepted_stage, accepted_at, accepted_status = (
                service.accepted_job_for_run(run_key)
            )
            return get_stage_projection(
                service.registry.resolve(run_key),
                stage_number,
                registry=service.registry,
                signer=service.signer,
                accepted_job_stage=accepted_stage,
                accepted_job_at=accepted_at,
                accepted_job_status=accepted_status,
                projects_root=service.projects_root,
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
                projects_root=service.projects_root,
            )
        except Exception as error:
            _raise_http(error)
            raise

    @app.get("/api/v1/runs/{run_key}/stages/5/overview")
    def stage05_overview(run_key: str, request: Request) -> Any:
        service = _state(request)
        try:
            root = service.registry.resolve(run_key)
            continuation = load_verified_project_scale_evidence(
                root,
                service.projects_root,
            )
            return get_filter_overview(
                root,
                registry=service.registry,
                policy_reevaluation=(
                    None
                    if continuation is None
                    else continuation.policy_reevaluation
                ),
            )
        except Exception as error:
            _raise_http(error)
            raise

    @app.get("/api/v1/runs/{run_key}/stages/5/strategies")
    def stage05_strategies(run_key: str, request: Request) -> Any:
        service = _state(request)
        try:
            root = service.registry.resolve(run_key)
            continuation = load_verified_project_scale_evidence(
                root,
                service.projects_root,
            )
            return list_filter_strategies(
                root,
                registry=service.registry,
                signer=service.signer,
                policy_reevaluation=(
                    None
                    if continuation is None
                    else continuation.policy_reevaluation
                ),
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
        raise HTTPException(
            status_code=409,
            detail={
                "code": "stage_locked",
                "reason": (
                    "正式运行不能在原运行工作区中复制、回写或快捷重跑。"
                    "请从“新建设计”创建名称不同的独立项目。"
                ),
                "run_key": run_key,
                "requested_project_id": payload.project_id,
            },
        )

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
            pending_stage = int(pending.stage_id.split("-", maxsplit=1)[0])
            service.assert_not_locked_by_downstream(run_key, pending_stage)
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
            service.assert_session_uses_latest_run(session, run_key)
            source = service.registry.resolve(run_key)
            service.assert_stage_configurable(run_key, 2)
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
            selected_run_id = payload.run_id or (
                datetime.now(tz=UTC).strftime("%Y%m%dt%H%M%Sz").lower()
                + "-stage02-regions"
            )
            try:
                job = service.jobs.launch(
                    operation="run",
                    config_path=generated,
                    run_root=source,
                    profile_path=service.profile_path,
                    runs_root=service.registry.runs_root,
                    run_id=selected_run_id,
                    continue_after_stage=1,
                    project_id=session.project_id,
                    accepted_run_key=run_key,
                    session_id=session.session_id,
                    session_root=service.sessions.root,
                    stage_number=2,
                    confirmed=True,
                )
            except Exception:
                quarantine_if_workspace_path(
                    generated,
                    operation="ui-stage02-region-revision",
                    reason="UI region revision 未能启动",
                )
                raise
            session = service.sessions.add_config_revision(
                session.session_id,
                stage_number=2,
                config_path=generated,
            )
            service.activate_project_config(session.project_id, generated)
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
            service.assert_not_locked_by_downstream(run_key, 2)
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
            service.assert_session_uses_latest_run(session, run_key)
            source = service.registry.resolve(run_key)
            service.assert_stage_configurable(run_key, next_stage)
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
            linked_remote_stage = (
                5
                if payload.executor_id is not None and next_stage == 4
                else 7
                if payload.executor_id is not None and next_stage == 6
                else None
            )
            materialize_continuation_config(
                source_run_root=source,
                destination=generated,
                stage_number=next_stage,
                execution_mode=payload.execution_mode,
                options=payload.options,
                continue_after_stage=continue_after_stage,
                linked_stage_number=linked_remote_stage,
            )
            remote_job: dict[str, Any] | None = None
            try:
                if payload.executor_id is not None:
                    if next_stage not in {4, 6}:
                        raise ConfigurationError(
                            "managed-ssh 执行位置只能用于 Stage 04 或 Stage 06"
                        )
                    pairing = RemoteExecutorRegistry(service.workspace).latest(
                        payload.executor_id
                    )
                    if pairing is None or pairing.state != "paired":
                        raise ConfigurationError("Suzhou2 尚未完成 SSH 配对")
                    if payload.controller_id != pairing.controller_id:
                        raise ConfigurationError("controller_id 与配对记录不一致")
                    selected_run_id = payload.run_id or (
                        datetime.now(tz=UTC).strftime("%Y%m%dt%H%M%Sz").lower()
                        + f"-stage{next_stage:02d}-managed"
                    )
                    submission = submit_managed_pipeline(
                        executor_id=payload.executor_id,
                        controller_id=payload.controller_id,
                        job_id=f"ui-{uuid4().hex[:16]}",
                        run_id=selected_run_id,
                        config_path=generated,
                        source_run=source,
                        profile_path=service.profile_path,
                        maximum_gpus=payload.maximum_gpus,
                        sync_mode=payload.sync_mode,
                    )
                    job = service.jobs.accept_external(
                        operation="managed-remote-run",
                        project_id=session.project_id,
                        stage_number=next_stage,
                        external_job_id=submission.job_id,
                        run_id=submission.run_id,
                        session_id=session.session_id,
                        status=submission.queue_status,
                    )
                    remote_job = submission.model_dump(mode="json")
                else:
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
                        project_id=session.project_id,
                        accepted_run_key=run_key,
                        session_id=session.session_id,
                        session_root=service.sessions.root,
                        stage_number=next_stage,
                        execution_target="local-current-host",
                        maximum_gpus=payload.maximum_gpus,
                        confirmed=True,
                    )
            except Exception:
                quarantine_if_workspace_path(
                    generated,
                    operation=f"ui-stage{next_stage:02d}-continuation",
                    reason="UI continuation 未能启动",
                )
                raise
            session = service.sessions.add_config_revision(
                session.session_id,
                stage_number=next_stage,
                config_path=generated,
            )
            service.activate_project_config(session.project_id, generated)
            session = service.sessions.update_status(
                session.session_id,
                status="running",
                current_stage=next_stage,
            )
            return {
                "session": session.model_dump(mode="json"),
                "job": job.model_dump(mode="json"),
                "execution_target": (
                    "local-current-host"
                    if payload.executor_id is None
                    else "managed-ssh"
                ),
                "remote_job": remote_job,
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
    browser_pymol_root = (
        Path(__file__).resolve().parent / "vendor" / "browser_pymol"
    )
    app.mount("/molstar", StaticFiles(directory=molstar_root), name="molstar")
    app.mount(
        "/pyodide",
        StaticFiles(directory=browser_pymol_root / "pyodide"),
        name="browser-pyodide",
    )
    app.mount(
        "/pymol-wasm",
        StaticFiles(directory=browser_pymol_root / "pymol-wasm"),
        name="browser-pymol-wasm",
    )
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
    port: int = 18769,
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
