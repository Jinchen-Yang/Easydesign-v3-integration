"""Project-local full-PML structure sessions and model adapters.

The assistant follows ChatPyMol's complete-document loop.  PML is the
visualization source of truth, while Stage 02 publication remains a separate,
deterministic mapping and human-approval boundary.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable, Literal
from urllib.parse import urlparse
from uuid import uuid4

import httpx
import yaml  # type: ignore[import-untyped]
from pydantic import BaseModel, ConfigDict, Field, model_validator

from easydesign.core import ConfigurationError
from easydesign.orchestration.task_tracking import (
    atomic_dump_runtime_model,
    load_latest_runtime_model,
)
from easydesign.ui.pml_skills import PmlSkill, render_pml_skills, select_pml_skills

ProviderId = Literal["deepseek", "zhipu-glm"]


class SceneVersionConflictError(ConfigurationError):
    """Raised when a PML scene edit targets a stale base version."""


ProposalKind = Literal[
    "pml-edit",
    "viewer-actions",
    "region-edit",
    "analysis-plan",
    "view-control",
    "explanation",
]

_SAFE_ID = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]{0,127}$")
_SAFE_COLOR = re.compile(r"^(?:[a-zA-Z][a-zA-Z0-9_-]{0,31}|#[0-9A-Fa-f]{6})$")
_SAFE_SELECTION = re.compile(r"^[a-zA-Z0-9_().,+:\-\s]+$")
_SAFE_LABEL_ARGUMENT = re.compile(
    r'^(?:""|name|"%s%s"\s*%\s*\(resn,\s*resi\))$',
    re.IGNORECASE,
)
_SAFE_SET_NAMES = frozenset(
    {
        "ambient",
        "antialias",
        "cartoon_transparency",
        "depth_cue",
        "fog",
        "fog_start",
        "label_color",
        "label_size",
        "orthoscopic",
        "ray_opaque_background",
        "ray_shadows",
        "ray_trace_mode",
        "reflect",
        "shininess",
        "specular",
        "sphere_color",
        "sphere_transparency",
        "stick_ball",
        "stick_ball_color",
        "stick_ball_ratio",
        "stick_color",
        "stick_radius",
        "stick_transparency",
        "surface_transparency",
        "transparency",
        "two_sided_lighting",
    }
)
_SAFE_COMMANDS = frozenset(
    {
        "as",
        "bg_color",
        "center",
        "color",
        "deselect",
        "hide",
        "label",
        "orient",
        "origin",
        "select",
        "set",
        "set_color",
        "set_view",
        "show",
        "spectrum",
        "unlabel",
        "unset",
        "zoom",
    }
)
_BLOCKED_COMMANDS = frozenset(
    {
        "alter",
        "create",
        "delete",
        "extract",
        "fetch",
        "load",
        "mpng",
        "png",
        "python",
        "quit",
        "rebuild",
        "reinitialize",
        "remove",
        "run",
        "save",
        "shell",
        "system",
    }
)
_MODEL_BLOCKED_COMMANDS = _BLOCKED_COMMANDS - {"create"}

_MANAGED_LINE_PREFIX = "# @easydesign"
_MANAGED_OBJECT_PATTERN = re.compile(r"\bobject=([A-Za-z_][A-Za-z0-9_.-]*)\b")
_CHAIN_PATTERN = re.compile(r"\bchain\s+([A-Za-z0-9_.-]+)", re.IGNORECASE)
_ALIGN_PATTERN = re.compile(r"^(?:align|super|cealign)\s+([^,\s]+)\s*,\s*([^,\s]+)", re.IGNORECASE)
_UNRESOLVED_PLACEHOLDER = re.compile(
    r"[<\[](?:object|selection|chain|residue|name)[>\]]",
    re.IGNORECASE,
)
_SIMPLE_SELECTION_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_.-]*$")
_BUILTIN_SELECTION_NAMES = frozenset(
    {
        "all",
        "none",
        "enabled",
        "visible",
        "polymer",
        "protein",
        "nucleic",
        "organic",
        "inorganic",
        "solvent",
        "hydro",
        "hetatm",
        "metals",
        "guide",
        "backbone",
        "sidechain",
    }
)


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _new_scene_version_id(revision: int) -> str:
    return f"scene-v{revision:06d}-{uuid4().hex[:8]}"


def _managed_lines(value: str) -> tuple[str, ...]:
    return tuple(
        line.strip() for line in value.splitlines() if line.strip().startswith(_MANAGED_LINE_PREFIX)
    )


def _managed_object_names(value: str) -> tuple[str, ...]:
    return tuple(
        match.group(1)
        for line in _managed_lines(value)
        if (match := _MANAGED_OBJECT_PATTERN.search(line)) is not None
    )


def _balanced(value: str) -> bool:
    depth = 0
    for character in value:
        if character == "(":
            depth += 1
        elif character == ")":
            depth -= 1
        if depth < 0:
            return False
    return depth == 0


def _simple_selection_name(value: str) -> str | None:
    candidate = value.strip()
    while (
        len(candidate) >= 2
        and candidate.startswith("(")
        and candidate.endswith(")")
        and _balanced(candidate[1:-1])
    ):
        candidate = candidate[1:-1].strip()
    return candidate if _SIMPLE_SELECTION_NAME.fullmatch(candidate) else None


def _selection_arguments(command: str) -> tuple[str, ...]:
    name, _, remainder = command.partition(" ")
    lower = name.lower()
    arguments = tuple(item.strip() for item in remainder.split(","))
    if lower in {"show", "hide", "as", "color"}:
        return arguments[1:2]
    if lower in {"center", "orient", "origin", "zoom", "unlabel"}:
        return arguments[:1]
    if lower == "label":
        return arguments[:1]
    if lower == "distance":
        return arguments[1:3]
    if lower == "create":
        return arguments[1:2]
    if lower == "set" and len(arguments) >= 3:
        return arguments[2:3]
    if lower == "spectrum" and len(arguments) >= 3:
        return arguments[2:3]
    return ()


class ViewerAction(BaseModel):
    """A display-only action that can be compiled to allow-listed PML."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    action: Literal[
        "representation",
        "color",
        "background",
        "focus",
        "orient",
        "center",
        "label",
        "unlabel",
        "select",
        "deselect",
    ]
    target: str = "all"
    value: str | None = None


class RegionEditOperation(BaseModel):
    """An explicit user-directed change to the editable A/B/C layer."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    operation: Literal["add", "remove", "toggle", "replace", "clear"]
    region_id: Literal["A", "B", "C"]
    numbering: Literal["label", "auth", "sequence", "uniprot"] = "label"
    chain: str | None = None
    residues: tuple[str, ...] = Field(default=(), max_length=10_000)

    @model_validator(mode="after")
    def require_residues_for_incremental_edits(self) -> RegionEditOperation:
        if self.operation in {"add", "remove", "toggle"} and not self.residues:
            raise ValueError("add/remove/toggle 区域操作必须包含至少一个残基")
        if self.operation == "clear" and self.residues:
            raise ValueError("clear 区域操作不应携带残基列表")
        return self


class ScientificAnalysisPlan(BaseModel):
    """A non-executing plan for existing deterministic Stage 02 methods."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    methods: tuple[Literal["sasa", "scannet"], ...] = Field(min_length=1, max_length=2)
    requires_confirmation: Literal[True] = True
    reason: str = Field(min_length=1, max_length=2_000)

    @model_validator(mode="after")
    def unique_methods(self) -> ScientificAnalysisPlan:
        if len(set(self.methods)) != len(self.methods):
            raise ValueError("Scientific analysis methods 不能重复")
        return self


class ViewControlOperation(BaseModel):
    """A reversible viewer-state operation over EasyDesign's saved display history."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    action: Literal["undo-last-view-action", "reset-default-view"]


class PmlEditProposal(BaseModel):
    """ChatPyMol-style full-scene PML edit proposed by the model."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    assistant_message: str = Field(min_length=1, max_length=8_000)
    summary: str = Field(min_length=1, max_length=240)
    conversation_title: str = Field(min_length=1, max_length=80)
    pml: str = Field(min_length=1, max_length=2_000_000)


class ChatPyMolEdit(BaseModel):
    """The sole response contract for new structure-assistant requests."""

    model_config = ConfigDict(frozen=True, extra="forbid", populate_by_name=True)

    assistant_message: str = Field(
        alias="assistantMessage",
        min_length=1,
        max_length=8_000,
    )
    summary: str = Field(min_length=1, max_length=240)
    conversation_title: str = Field(
        alias="conversationTitle",
        min_length=1,
        max_length=80,
    )
    pml: str = Field(min_length=1, max_length=2_000_000)


class ReferenceStructure(BaseModel):
    """A visual-only reference object available to the Stage 2 scene."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    object_id: str
    role: Literal["target", "reference"]
    object_name: str
    filename: str
    file_format: str
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source: str = Field(min_length=1, max_length=256)
    created_at: datetime


class SceneVersion(BaseModel):
    """A full PML scene snapshot, compatible with ChatPyMol's version model."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    version_id: str
    revision: int = Field(ge=1)
    parent_version_id: str | None = None
    base_version_id: str | None = None
    actor: Literal["human", "ai", "viewer", "system"] = "system"
    source: str = Field(min_length=1, max_length=120)
    provider: ProviderId | None = None
    model: str | None = None
    skill_ids: tuple[str, ...] = ()
    conversation_title: str | None = Field(default=None, max_length=80)
    summary: str = Field(min_length=1, max_length=240)
    pml: str = Field(min_length=1, max_length=2_000_000)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    created_at: datetime


class AssistantProposal(BaseModel):
    """Legacy typed proposal retained for old records and server-derived plans."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    proposal_id: str = ""
    kind: ProposalKind
    explanation: str = Field(min_length=1, max_length=8_000)
    pml_edit: PmlEditProposal | None = None
    viewer_actions: tuple[ViewerAction, ...] = ()
    region_operations: tuple[RegionEditOperation, ...] = ()
    analysis_plan: ScientificAnalysisPlan | None = None
    view_control: ViewControlOperation | None = None

    @model_validator(mode="after")
    def match_kind(self) -> AssistantProposal:
        if self.kind == "pml-edit" and self.pml_edit is None:
            raise ValueError("pml-edit proposal 必须包含完整 PML 修改")
        if self.kind == "viewer-actions" and not self.viewer_actions:
            raise ValueError("viewer-actions proposal 必须包含动作")
        if self.kind == "region-edit" and not self.region_operations:
            raise ValueError("region-edit proposal 必须包含明确区域操作")
        if self.kind == "analysis-plan" and self.analysis_plan is None:
            raise ValueError("analysis-plan proposal 必须包含计划")
        if self.kind == "view-control" and self.view_control is None:
            raise ValueError("view-control proposal 必须包含视图控制操作")
        executable = (
            self.pml_edit is not None
            or bool(self.viewer_actions)
            or bool(self.region_operations)
            or self.analysis_plan is not None
            or self.view_control is not None
        )
        if self.kind == "explanation" and executable:
            raise ValueError("explanation proposal 不能携带可执行操作")
        if self.kind != "pml-edit" and self.pml_edit is not None:
            raise ValueError("只有 pml-edit proposal 可以携带完整 PML 修改")
        if self.kind != "view-control" and self.view_control is not None:
            raise ValueError("只有 view-control proposal 可以携带视图控制操作")
        return self


class InteractionMessage(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    message_id: str
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=20_000)
    created_at: datetime
    provider: ProviderId | None = None
    model: str | None = None
    request_id: str | None = None
    version_id: str | None = None
    proposal: AssistantProposal | None = None


class PmlRevision(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    revision: int = Field(ge=1)
    pml: str = Field(max_length=1_000_000)
    source: Literal["viewer", "assistant", "expert-console"]
    viewer_scope: Literal["pymol"] = "pymol"
    created_at: datetime


class ViewStateRevision(BaseModel):
    """Viewer-neutral display state replayed by PyMOL and Mol* adapters."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    revision: int = Field(ge=1)
    actions: tuple[ViewerAction, ...] = Field(min_length=1)
    source: Literal["viewer", "assistant"]
    created_at: datetime


class StructureInteractionSession(BaseModel):
    """Mutable product workflow represented by immutable full snapshots."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["0.1", "0.2", "0.3", "0.4"] = "0.4"
    session_id: str
    project_id: str
    run_key: str
    stage_number: Literal[1, 2]
    target_structure_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    residue_mapping_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    selected_provider: ProviderId | None = None
    messages: tuple[InteractionMessage, ...] = ()
    pml_revisions: tuple[PmlRevision, ...] = ()
    view_state_revisions: tuple[ViewStateRevision, ...] = ()
    scene_versions: tuple[SceneVersion, ...] = ()
    active_scene_version_id: str | None = None
    reference_structures: tuple[ReferenceStructure, ...] = ()
    current_regions: dict[str, tuple[int, ...]] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class AssistantProviderSecret(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["0.1"] = "0.1"
    provider: ProviderId
    model: str = Field(min_length=1, max_length=256)
    base_url: str = Field(min_length=1, max_length=2_048)
    api_key: str = Field(min_length=1, max_length=8_192)
    configured_at: datetime


class AssistantProviderStatus(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    provider: ProviderId
    configured: bool
    model: str | None = None
    base_url: str | None = None
    api_key_masked: str | None = None


class PlatformAssistantConfig(BaseModel):
    """Deployment-owned provider configuration loaded only on the server."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["0.1"] = "0.1"
    provider: ProviderId
    model: str = Field(min_length=1, max_length=256)
    base_url: str = Field(min_length=1, max_length=2_048)
    api_key: str = Field(min_length=1, max_length=8_192)

    @model_validator(mode="after")
    def validate_endpoint(self) -> PlatformAssistantConfig:
        parsed = urlparse(self.base_url)
        if parsed.scheme != "https" or not parsed.netloc:
            raise ValueError("模型 API endpoint 必须是完整 HTTPS URL")
        if parsed.username or parsed.password:
            raise ValueError("模型 API endpoint 不能内嵌凭据")
        return self


class PlatformAssistantStatus(BaseModel):
    """Public status that never exposes provider or secret identity."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    available: bool
    service_name: Literal["EasyDesign 结构助手"] = "EasyDesign 结构助手"
    detail: str


class AssistantProviderStore:
    """Revision-only repository-local secret storage."""

    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, provider: ProviderId) -> Path:
        return self.root / provider / "provider.json"

    def configure(
        self,
        *,
        provider: ProviderId,
        model: str,
        base_url: str,
        api_key: str,
        configured_at: datetime | None = None,
    ) -> AssistantProviderStatus:
        parsed = urlparse(base_url)
        if parsed.scheme != "https" or not parsed.netloc:
            raise ConfigurationError("模型 API endpoint 必须是完整 HTTPS URL")
        secret = AssistantProviderSecret(
            provider=provider,
            model=model.strip(),
            base_url=base_url.rstrip("/"),
            api_key=api_key.strip(),
            configured_at=configured_at or datetime.now(tz=UTC),
        )
        destination = atomic_dump_runtime_model(secret, self._path(provider))
        try:
            os.chmod(destination, 0o600)
            revision_root = destination.with_name(f"{destination.name}.revisions")
            for revision in revision_root.glob("revision-*.json"):
                os.chmod(revision, 0o600)
        except OSError as error:
            raise ConfigurationError("无法收紧模型 API secret 文件权限") from error
        return self.status(provider)

    def load(self, provider: ProviderId) -> AssistantProviderSecret:
        path = self._path(provider)
        if not path.is_file():
            raise ConfigurationError(f"{provider} API 尚未配置")
        value = load_latest_runtime_model(path, AssistantProviderSecret)
        return value

    def status(self, provider: ProviderId) -> AssistantProviderStatus:
        try:
            secret = self.load(provider)
        except ConfigurationError:
            return AssistantProviderStatus(provider=provider, configured=False)
        visible = secret.api_key[-4:] if len(secret.api_key) >= 4 else "****"
        return AssistantProviderStatus(
            provider=provider,
            configured=True,
            model=secret.model,
            base_url=secret.base_url,
            api_key_masked=f"••••{visible}",
        )

    def statuses(self) -> tuple[AssistantProviderStatus, ...]:
        return (self.status("deepseek"), self.status("zhipu-glm"))

    @property
    def platform_path(self) -> Path:
        return self.root / "platform-provider.yaml"

    def load_platform(self) -> AssistantProviderSecret:
        """Load the single deployment-owned provider without client selection."""

        path = self.platform_path
        if path.is_symlink():
            raise ConfigurationError("平台结构助手配置不能是符号链接")
        if not path.is_file():
            raise ConfigurationError("平台结构助手尚未由部署者启用")
        if os.name == "posix" and path.stat().st_mode & 0o077:
            raise ConfigurationError("平台结构助手配置权限过宽；请设置为 0600")
        try:
            payload = yaml.safe_load(path.read_text(encoding="utf-8"))
            config = PlatformAssistantConfig.model_validate(payload)
        except (OSError, yaml.YAMLError, ValueError) as error:
            raise ConfigurationError("平台结构助手配置无法验证") from error
        return AssistantProviderSecret(
            provider=config.provider,
            model=config.model,
            base_url=config.base_url.rstrip("/"),
            api_key=config.api_key,
            configured_at=datetime.fromtimestamp(path.stat().st_mtime, tz=UTC),
        )

    def platform_status(self) -> PlatformAssistantStatus:
        try:
            self.load_platform()
        except ConfigurationError as error:
            return PlatformAssistantStatus(
                available=False,
                detail=str(error),
            )
        return PlatformAssistantStatus(
            available=True,
            detail="平台服务已就绪，使用者无需提供 API Key。",
        )


class StructureInteractionStore:
    """Project-local revision-only interaction storage."""

    def __init__(self, projects_root: Path) -> None:
        self.projects_root = projects_root.resolve()
        self.projects_root.mkdir(parents=True, exist_ok=True)
        self._create_lock = threading.Lock()

    def _project_root(self, project_id: str) -> Path:
        if not _SAFE_ID.fullmatch(project_id):
            raise ConfigurationError("无效的项目编号")
        return self.projects_root / project_id

    def _session_root(self, project_id: str, session_id: str) -> Path:
        if not session_id.startswith("structure-session-") or not _SAFE_ID.fullmatch(session_id):
            raise ConfigurationError("无效的结构交互会话编号")
        return self._project_root(project_id) / "interactive-sessions" / session_id

    def _locate(self, session_id: str) -> Path:
        if not session_id.startswith("structure-session-") or not _SAFE_ID.fullmatch(session_id):
            raise ConfigurationError("无效的结构交互会话编号")
        matches = tuple(
            self.projects_root.glob(f"*/interactive-sessions/{session_id}/session.json")
        )
        if len(matches) != 1:
            raise ConfigurationError(f"结构交互会话不存在或不唯一: {session_id}")
        return matches[0]

    def create(
        self,
        *,
        project_id: str,
        run_key: str,
        stage_number: int,
        target_structure_sha256: str,
        residue_mapping_sha256: str,
        current_regions: dict[str, tuple[int, ...]] | None = None,
        created_at: datetime | None = None,
    ) -> StructureInteractionSession:
        if stage_number not in {1, 2}:
            raise ConfigurationError("结构交互只支持 Stage 01/02")
        selected_stage: Literal[1, 2] = 1 if stage_number == 1 else 2
        now = created_at or datetime.now(tz=UTC)
        value = StructureInteractionSession(
            session_id=f"structure-session-{uuid4().hex[:16]}",
            project_id=project_id,
            run_key=run_key,
            stage_number=selected_stage,
            target_structure_sha256=target_structure_sha256,
            residue_mapping_sha256=residue_mapping_sha256,
            current_regions=normalize_regions(current_regions or {}),
            created_at=now,
            updated_at=now,
        )
        root = self._session_root(project_id, value.session_id)
        root.mkdir(parents=True, exist_ok=False)
        atomic_dump_runtime_model(value, root / "session.json")
        return value

    def latest_for(
        self,
        *,
        project_id: str,
        run_key: str,
        stage_number: int,
        target_structure_sha256: str,
        residue_mapping_sha256: str,
    ) -> StructureInteractionSession | None:
        roots = (self._project_root(project_id) / "interactive-sessions").glob(
            "structure-session-*/session.json"
        )
        matches: list[StructureInteractionSession] = []
        for path in roots:
            try:
                value = load_latest_runtime_model(
                    path,
                    StructureInteractionSession,
                )
            except (OSError, ValueError):
                continue
            if (
                value.run_key == run_key
                and value.stage_number == stage_number
                and value.target_structure_sha256 == target_structure_sha256
                and value.residue_mapping_sha256 == residue_mapping_sha256
            ):
                matches.append(value)
        return max(matches, key=lambda item: item.updated_at) if matches else None

    def get_or_create(
        self,
        *,
        project_id: str,
        run_key: str,
        stage_number: int,
        target_structure_sha256: str,
        residue_mapping_sha256: str,
        current_regions: dict[str, tuple[int, ...]] | None = None,
    ) -> StructureInteractionSession:
        """Idempotent within the service, including React StrictMode retries."""

        with self._create_lock:
            existing = self.latest_for(
                project_id=project_id,
                run_key=run_key,
                stage_number=stage_number,
                target_structure_sha256=target_structure_sha256,
                residue_mapping_sha256=residue_mapping_sha256,
            )
            if existing is not None:
                return existing
            return self.create(
                project_id=project_id,
                run_key=run_key,
                stage_number=stage_number,
                target_structure_sha256=target_structure_sha256,
                residue_mapping_sha256=residue_mapping_sha256,
                current_regions=current_regions,
            )

    def load(self, session_id: str) -> StructureInteractionSession:
        return load_latest_runtime_model(self._locate(session_id), StructureInteractionSession)

    def proposal(
        self,
        session_id: str,
        proposal_id: str,
    ) -> AssistantProposal:
        current = self.load(session_id)
        proposals = tuple(
            message.proposal
            for message in current.messages
            if message.proposal is not None and message.proposal.proposal_id == proposal_id
        )
        if len(proposals) != 1:
            raise ConfigurationError("待应用的助手 proposal 不存在或不唯一")
        return proposals[0]

    def _publish(self, value: StructureInteractionSession) -> StructureInteractionSession:
        if value.schema_version != "0.4":
            value = value.model_copy(update={"schema_version": "0.4"})
        path = self._session_root(value.project_id, value.session_id) / "session.json"
        atomic_dump_runtime_model(value, path)
        return value

    def active_scene_version(
        self,
        session_id: str,
    ) -> SceneVersion | None:
        current = self.load(session_id)
        if current.active_scene_version_id:
            for version in current.scene_versions:
                if version.version_id == current.active_scene_version_id:
                    return version
        return current.scene_versions[-1] if current.scene_versions else None

    def ensure_scene(
        self,
        session_id: str,
        *,
        pml: str,
        target_object: ReferenceStructure,
        summary: str = "初始化 Stage 2 PML 场景",
        updated_at: datetime | None = None,
    ) -> StructureInteractionSession:
        current = self.load(session_id)
        if current.scene_versions and current.active_scene_version_id:
            return current
        now = updated_at or datetime.now(tz=UTC)
        normalized = validate_scene_pml(pml)
        version = SceneVersion(
            version_id=_new_scene_version_id(1),
            revision=1,
            parent_version_id=None,
            base_version_id=None,
            actor="system",
            source="easydesign-stage2-bootstrap",
            summary=summary,
            pml=normalized,
            sha256=_sha256_text(normalized),
            created_at=now,
        )
        references = tuple(
            item
            for item in current.reference_structures
            if item.object_id != target_object.object_id
        ) + (target_object,)
        return self._publish(
            current.model_copy(
                update={
                    "scene_versions": (version,),
                    "active_scene_version_id": version.version_id,
                    "reference_structures": references,
                    "updated_at": now,
                }
            )
        )

    def save_scene_version(
        self,
        session_id: str,
        *,
        pml: str,
        actor: Literal["human", "ai", "viewer", "system"],
        source: str,
        summary: str,
        base_version_id: str | None = None,
        parent_version_id: str | None = None,
        provider: ProviderId | None = None,
        model: str | None = None,
        skill_ids: tuple[str, ...] = (),
        conversation_title: str | None = None,
        known_object_names: tuple[str, ...] = (),
        known_chain_ids: tuple[str, ...] = (),
        allowed_new_managed_lines: tuple[str, ...] = (),
        reference_structures: tuple[ReferenceStructure, ...] | None = None,
        current_regions: dict[str, tuple[int, ...]] | None = None,
        force_new_version: bool = False,
        updated_at: datetime | None = None,
    ) -> tuple[StructureInteractionSession, SceneVersion]:
        current = self.load(session_id)
        active = None
        if current.active_scene_version_id:
            active = next(
                (
                    item
                    for item in current.scene_versions
                    if item.version_id == current.active_scene_version_id
                ),
                None,
            )
        if base_version_id is not None and base_version_id != current.active_scene_version_id:
            raise SceneVersionConflictError("PML 场景已经被其他操作更新；请刷新后重试")
        previous_pml = active.pml if active is not None else None
        normalized = validate_scene_pml(
            pml,
            previous_pml=previous_pml,
            known_object_names=known_object_names,
            known_chain_ids=known_chain_ids,
            allowed_new_managed_lines=allowed_new_managed_lines,
        )
        if active is not None and normalized == active.pml and not force_new_version:
            return current, active
        now = updated_at or datetime.now(tz=UTC)
        revision = len(current.scene_versions) + 1
        version = SceneVersion(
            version_id=_new_scene_version_id(revision),
            revision=revision,
            parent_version_id=parent_version_id or current.active_scene_version_id,
            base_version_id=base_version_id,
            actor=actor,
            source=source[:120] or "scene-edit",
            provider=provider,
            model=model,
            skill_ids=tuple(skill_ids),
            conversation_title=(
                conversation_title[:80] if conversation_title is not None else None
            ),
            summary=summary[:240] or "更新 PML 场景",
            pml=normalized,
            sha256=_sha256_text(normalized),
            created_at=now,
        )
        update_payload: dict[str, Any] = {
            "scene_versions": current.scene_versions + (version,),
            "active_scene_version_id": version.version_id,
            "updated_at": now,
        }
        if reference_structures is not None:
            update_payload["reference_structures"] = reference_structures
        if current_regions is not None:
            update_payload["current_regions"] = normalize_regions(current_regions)
        updated = self._publish(current.model_copy(update=update_payload))
        return updated, version

    def restore_scene_version(
        self,
        session_id: str,
        *,
        version_id: str,
        base_version_id: str | None = None,
        current_regions: dict[str, tuple[int, ...]] | None = None,
        updated_at: datetime | None = None,
    ) -> tuple[StructureInteractionSession, SceneVersion]:
        current = self.load(session_id)
        target = next(
            (item for item in current.scene_versions if item.version_id == version_id),
            None,
        )
        if target is None:
            raise ConfigurationError("要恢复的 PML 场景版本不存在")
        updated, version = self.save_scene_version(
            session_id,
            pml=target.pml,
            actor="human",
            source="history-restore",
            summary=f"恢复到 PML 场景版本 {target.revision}",
            base_version_id=base_version_id,
            parent_version_id=target.version_id,
            current_regions=current_regions,
            updated_at=updated_at,
        )
        now = updated_at or datetime.now(tz=UTC)
        message = InteractionMessage(
            message_id=f"message-{uuid4().hex[:16]}",
            role="user",
            content=f"恢复到 PML 场景版本 {target.revision}，形成新版本 {version.revision}。",
            created_at=now,
            version_id=version.version_id,
        )
        updated = self._publish(
            updated.model_copy(
                update={
                    "messages": updated.messages + (message,),
                    "updated_at": now,
                }
            )
        )
        return updated, version

    def append_exchange(
        self,
        session_id: str,
        *,
        user_text: str,
        proposal: AssistantProposal,
        provider: ProviderId,
        model: str,
        request_id: str | None,
        version_id: str | None = None,
        updated_at: datetime | None = None,
    ) -> StructureInteractionSession:
        current = self.load(session_id)
        now = updated_at or datetime.now(tz=UTC)
        proposal_value = proposal.model_copy(
            update={"proposal_id": proposal.proposal_id or f"proposal-{uuid4().hex[:16]}"}
        )
        user_message = InteractionMessage(
            message_id=f"message-{uuid4().hex[:16]}",
            role="user",
            content=user_text,
            created_at=now,
        )
        assistant_message = InteractionMessage(
            message_id=f"message-{uuid4().hex[:16]}",
            role="assistant",
            content=proposal_value.explanation,
            created_at=now,
            provider=provider,
            model=model,
            request_id=request_id,
            version_id=version_id,
            proposal=proposal_value,
        )
        return self._publish(
            current.model_copy(
                update={
                    "selected_provider": provider,
                    "messages": current.messages + (user_message, assistant_message),
                    "updated_at": now,
                }
            )
        )

    def append_pml_exchange(
        self,
        session_id: str,
        *,
        user_text: str,
        proposal: AssistantProposal,
        provider: ProviderId,
        model: str,
        request_id: str | None,
        known_object_names: tuple[str, ...] = (),
        known_chain_ids: tuple[str, ...] = (),
        updated_at: datetime | None = None,
    ) -> StructureInteractionSession:
        if proposal.kind != "pml-edit" or proposal.pml_edit is None:
            raise ConfigurationError("只有 pml-edit proposal 可以直接提交 PML 场景版本")
        current = self.load(session_id)
        updated, version = self.save_scene_version(
            session_id,
            pml=proposal.pml_edit.pml,
            actor="ai",
            source=f"assistant:{provider}",
            summary=proposal.pml_edit.summary,
            base_version_id=current.active_scene_version_id,
            known_object_names=known_object_names,
            known_chain_ids=known_chain_ids,
            updated_at=updated_at,
        )
        return self.append_exchange(
            session_id,
            user_text=user_text,
            proposal=proposal.model_copy(
                update={"explanation": proposal.pml_edit.assistant_message}
            ),
            provider=provider,
            model=model,
            request_id=request_id,
            version_id=version.version_id,
            updated_at=updated_at,
        )

    def append_chatpymol_exchange(
        self,
        session_id: str,
        *,
        user_text: str,
        edit: ChatPyMolEdit,
        provider: ProviderId,
        model: str,
        request_id: str | None,
        skill_ids: tuple[str, ...],
        proposal: AssistantProposal | None = None,
        known_object_names: tuple[str, ...] = (),
        known_chain_ids: tuple[str, ...] = (),
        current_regions: dict[str, tuple[int, ...]] | None = None,
        updated_at: datetime | None = None,
    ) -> StructureInteractionSession:
        """Publish one immutable full-PML version and its conversation exchange."""

        current = self.load(session_id)
        updated, version = self.save_scene_version(
            session_id,
            pml=edit.pml,
            actor="ai",
            source=f"assistant:{provider}",
            provider=provider,
            model=model,
            skill_ids=skill_ids,
            conversation_title=edit.conversation_title,
            summary=edit.summary,
            base_version_id=current.active_scene_version_id,
            known_object_names=known_object_names,
            known_chain_ids=known_chain_ids,
            current_regions=current_regions,
            force_new_version=True,
            updated_at=updated_at,
        )
        now = updated_at or datetime.now(tz=UTC)
        user_message = InteractionMessage(
            message_id=f"message-{uuid4().hex[:16]}",
            role="user",
            content=user_text,
            created_at=now,
        )
        assistant_message = InteractionMessage(
            message_id=f"message-{uuid4().hex[:16]}",
            role="assistant",
            content=edit.assistant_message,
            created_at=now,
            provider=provider,
            model=model,
            request_id=request_id,
            version_id=version.version_id,
            proposal=(
                proposal.model_copy(
                    update={"proposal_id": (proposal.proposal_id or f"proposal-{uuid4().hex[:16]}")}
                )
                if proposal is not None
                else None
            ),
        )
        update_payload: dict[str, Any] = {
            "selected_provider": provider,
            "messages": updated.messages + (user_message, assistant_message),
            "updated_at": now,
        }
        return self._publish(updated.model_copy(update=update_payload))

    def apply_proposal(
        self,
        session_id: str,
        *,
        proposal_id: str,
        pml: str | None = None,
        viewer_actions: tuple[ViewerAction, ...] | None = None,
        current_regions: dict[str, tuple[int, ...]] | None = None,
        view_control: ViewControlOperation | None = None,
        source: Literal["viewer", "assistant", "expert-console"] = "assistant",
        updated_at: datetime | None = None,
    ) -> StructureInteractionSession:
        current = self.load(session_id)
        self.proposal(session_id, proposal_id)
        now = updated_at or datetime.now(tz=UTC)
        revisions = current.pml_revisions
        view_revisions = current.view_state_revisions
        if pml is not None:
            validated = validate_safe_pml(pml)
            revisions = revisions + (
                PmlRevision(
                    revision=len(revisions) + 1,
                    pml=validated,
                    source=source,
                    created_at=now,
                ),
            )
        if viewer_actions is not None:
            validate_common_viewer_actions(viewer_actions)
            view_revisions = view_revisions + (
                ViewStateRevision(
                    revision=len(view_revisions) + 1,
                    actions=viewer_actions,
                    source="assistant" if source == "assistant" else "viewer",
                    created_at=now,
                ),
            )
        if view_control is not None:
            if view_control.action == "undo-last-view-action":
                if not view_revisions:
                    raise ConfigurationError("当前没有可撤销的显示动作")
                view_revisions = view_revisions[:-1]
            elif view_control.action == "reset-default-view":
                view_revisions = ()
                revisions = ()
        normalized_regions = current.current_regions
        if current_regions is not None:
            normalized_regions = normalize_regions(current_regions)
        return self._publish(
            current.model_copy(
                update={
                    "pml_revisions": revisions,
                    "view_state_revisions": view_revisions,
                    "current_regions": normalized_regions,
                    "updated_at": now,
                }
            )
        )

    def append_pml(
        self,
        session_id: str,
        *,
        pml: str,
        source: Literal["viewer", "assistant", "expert-console"],
        updated_at: datetime | None = None,
    ) -> StructureInteractionSession:
        current = self.load(session_id)
        now = updated_at or datetime.now(tz=UTC)
        active = None
        if current.active_scene_version_id:
            active = next(
                (
                    item
                    for item in current.scene_versions
                    if item.version_id == current.active_scene_version_id
                ),
                None,
            )
        validated = validate_scene_pml(
            pml,
            known_object_names=(() if active is None else _managed_object_names(active.pml)),
        )
        commands = tuple(
            command
            for command in split_pml_commands(validated)
            if command.strip().lower() != "deselect"
        )
        if not commands:
            return current
        validated = "\n".join(commands) + "\n"
        if active is not None:
            active_commands = tuple(
                command
                for command in split_pml_commands(active.pml)
                if command.strip().lower() != "deselect"
            )
            if (
                len(active_commands) >= len(commands)
                and active_commands[-len(commands) :] == commands
            ):
                return current
        revision = PmlRevision(
            revision=len(current.pml_revisions) + 1,
            pml=validated,
            source=source,
            created_at=now,
        )
        if active is not None:
            next_pml = (
                f"{active.pml.rstrip()}\n\n# @chatpymol native-pymol source={source}\n{validated}"
            )
            updated, _version = self.save_scene_version(
                session_id,
                pml=next_pml,
                actor="viewer" if source == "viewer" else "human",
                source=f"native-pymol:{source}",
                summary="原生 PyMOL 操作",
                base_version_id=current.active_scene_version_id,
                updated_at=now,
            )
            current = updated
        return self._publish(
            current.model_copy(
                update={
                    "pml_revisions": current.pml_revisions + (revision,),
                    "updated_at": now,
                }
            )
        )


def normalize_regions(values: dict[str, tuple[int, ...]]) -> dict[str, tuple[int, ...]]:
    owner: dict[int, str] = {}
    normalized: dict[str, tuple[int, ...]] = {}
    for region_id in ("A", "B", "C"):
        residues = tuple(sorted(set(int(value) for value in values.get(region_id, ()))))
        if any(value < 1 for value in residues):
            raise ConfigurationError("区域残基编号必须为正整数")
        for residue in residues:
            previous = owner.get(residue)
            if previous is not None:
                raise ConfigurationError(f"残基 {residue} 同时属于区域 {previous} 和 {region_id}")
            owner[residue] = region_id
        if residues:
            normalized[region_id] = residues
    return normalized


def split_pml_commands(value: str) -> tuple[str, ...]:
    commands: list[str] = []
    pending = ""
    for raw_line in value.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        pending += (" " if pending else "") + line.removesuffix("\\").strip()
        if line.endswith("\\"):
            continue
        for part in pending.split(";"):
            command = part.strip()
            if command:
                commands.append(command)
        pending = ""
    if pending:
        commands.append(pending)
    return tuple(commands)


def validate_safe_pml(value: str) -> str:
    """Accept only display/selection PML and return canonical one-command lines."""

    commands = split_pml_commands(value)
    if not commands:
        raise ConfigurationError("PML 没有可执行的显示命令")
    canonical: list[str] = []
    for command in commands:
        name = command.split(maxsplit=1)[0].lower()
        if name in _BLOCKED_COMMANDS or name not in _SAFE_COMMANDS:
            raise ConfigurationError(f"PML 命令不在显示安全列表中: {name}")
        if name in {"set", "unset"}:
            remainder = command.split(maxsplit=1)[1] if " " in command else ""
            setting = remainder.split(",", maxsplit=1)[0].strip().lower()
            if setting not in _SAFE_SET_NAMES:
                raise ConfigurationError(f"PyMOL set 参数不在显示安全列表中: {setting}")
        if name == "select":
            if "," not in command:
                raise ConfigurationError("select 必须显式给出选择名称和表达式")
            selection = command.split(",", maxsplit=1)[1]
            if not _SAFE_SELECTION.fullmatch(selection):
                raise ConfigurationError("select 表达式包含不允许的字符")
        if name == "label":
            if "," not in command:
                raise ConfigurationError("label 必须显式给出目标和安全标签模板")
            argument = command.split(",", maxsplit=1)[1].strip()
            if not _SAFE_LABEL_ARGUMENT.fullmatch(argument):
                raise ConfigurationError("label 表达式不在安全模板列表中")
        canonical.append(command)
    return "\n".join(canonical) + "\n"


def validate_scene_pml(
    value: str,
    *,
    previous_pml: str | None = None,
    known_object_names: tuple[str, ...] = (),
    known_chain_ids: tuple[str, ...] = (),
    allowed_new_managed_lines: tuple[str, ...] = (),
) -> str:
    """Validate a native full-PML scene using ChatPyMol's minimal safety boundary."""

    if len(value) > 2_000_000:
        raise ConfigurationError("PML 场景不能超过 2 MB")
    normalized = f"{value.replace(chr(13) + chr(10), chr(10)).strip()}\n"
    if previous_pml is not None:
        previous_managed = set(_managed_lines(previous_pml))
        next_managed = set(_managed_lines(normalized))
        missing = previous_managed - next_managed
        allowed_added = {line.strip() for line in allowed_new_managed_lines}
        added = next_managed - previous_managed - allowed_added
        if missing:
            raise ConfigurationError("模型删除了受保护的 EasyDesign 结构管理行")
        if added:
            raise ConfigurationError(
                "模型不能伪造新的 EasyDesign 结构管理行；请通过上传/RCSB 接口添加参考结构"
            )
    commands = split_pml_commands(normalized)
    if not commands:
        raise ConfigurationError("PML 场景没有可执行的显示命令")
    object_names = set(known_object_names) | set(_managed_object_names(normalized))
    chain_ids = set(known_chain_ids)
    previous_commands = set(split_pml_commands(previous_pml or ""))
    known_selection_names = set(_BUILTIN_SELECTION_NAMES) | object_names
    for command in commands:
        if not _balanced(command):
            raise ConfigurationError(f"PML 命令括号不匹配: {command[:160]}")
        name = command.split(maxsplit=1)[0].lower()
        if name in _MODEL_BLOCKED_COMMANDS and command not in previous_commands:
            raise ConfigurationError(f"PML 命令触及系统、文件或网络边界: {name}")
        if _UNRESOLVED_PLACEHOLDER.search(command):
            raise ConfigurationError(f"PML 仍包含未替换占位符: {command[:160]}")
        if name == "select" and "," not in command:
            raise ConfigurationError("select 必须显式给出选择名称和表达式")
        if name == "label" and "," not in command:
            raise ConfigurationError("label 必须显式给出目标和标签表达式")
        if name == "select":
            selection_name = command.partition(" ")[2].partition(",")[0].strip()
            if not _SIMPLE_SELECTION_NAME.fullmatch(selection_name):
                raise ConfigurationError("select 名称不是有效的 PyMOL identifier")
            expression = command.partition(",")[2]
            simple_expression = _simple_selection_name(expression)
            if simple_expression is not None and simple_expression not in known_selection_names:
                raise ConfigurationError(
                    f"PML 引用了当前场景中不存在的对象或 selection: {simple_expression}"
                )
            known_selection_names.add(selection_name)
        if name == "create":
            destination = command.partition(" ")[2].partition(",")[0].strip()
            if not _SIMPLE_SELECTION_NAME.fullmatch(destination):
                raise ConfigurationError("create 目标不是有效的 PyMOL object identifier")
            if destination in object_names:
                raise ConfigurationError(f"PML 不能用 create 覆盖受管理结构对象: {destination}")
            known_selection_names.add(destination)
        for argument in _selection_arguments(command):
            simple_argument = _simple_selection_name(argument)
            if simple_argument is not None and simple_argument not in known_selection_names:
                raise ConfigurationError(
                    f"PML 引用了当前场景中不存在的对象或 selection: {simple_argument}"
                )
        if command not in previous_commands and chain_ids:
            for chain_id in _CHAIN_PATTERN.findall(command):
                if chain_id not in chain_ids:
                    raise ConfigurationError(f"PML 引用了当前结构中不存在的链: {chain_id}")
        if object_names:
            match = _ALIGN_PATTERN.match(command)
            if match:
                for object_name in match.groups():
                    if object_name not in object_names:
                        raise ConfigurationError(f"PML 比对命令引用了不存在的对象: {object_name}")
    return normalized


def derive_scene_summary(pml: str, object_names: tuple[str, ...] = ()) -> dict[str, Any]:
    """Small ChatPyMol-style scene summary for model context and diagnostics."""

    objects: dict[str, dict[str, Any]] = {
        name: {"name": name, "representations": [], "colors": []} for name in object_names
    }
    if not objects:
        objects["target"] = {"name": "target", "representations": [], "colors": []}
    scene: dict[str, Any] = {
        "schema_version": 1,
        "objects": list(objects.values()),
        "selections": [],
        "commands": [],
        "background": None,
    }
    for command in split_pml_commands(pml):
        scene["commands"].append(command)
        name, _, rest = command.partition(" ")
        lower = name.lower()
        if lower == "bg_color":
            scene["background"] = rest.strip()
        elif lower == "show":
            representation, _, selection = rest.partition(",")
            selection = selection.strip() or "all"
            for item in objects.values():
                if selection == "all" or item["name"] in selection:
                    item["representations"].append(representation.strip())
        elif lower == "color":
            color, _, selection = rest.partition(",")
            selection = selection.strip() or "all"
            for item in objects.values():
                if selection == "all" or item["name"] in selection:
                    item["colors"].append({"color": color.strip(), "selection": selection})
        elif lower == "select":
            name_part, _, expression = rest.partition(",")
            scene["selections"].append(
                {
                    "name": name_part.strip(),
                    "expression": expression.strip(),
                }
            )
    for item in objects.values():
        item["representations"] = sorted(set(item["representations"]))
    return scene


def compile_viewer_actions(actions: tuple[ViewerAction, ...]) -> str:
    commands: list[str] = []
    representation = {
        "cartoon": "cartoon",
        "surface": "surface",
        "stick": "sticks",
        "sticks": "sticks",
    }
    for action in actions:
        target = action.target.strip() or "all"
        if not _SAFE_SELECTION.fullmatch(target):
            raise ConfigurationError("ViewerAction target 包含不允许的字符")
        if action.action == "representation":
            selected = representation.get((action.value or "").lower())
            if selected is None:
                raise ConfigurationError("不支持的结构显示方式")
            commands.append(f"hide everything, {target}")
            commands.append(f"show {selected}, {target}")
        elif action.action == "color":
            color = action.value or ""
            if not _SAFE_COLOR.fullmatch(color):
                raise ConfigurationError("不支持的颜色")
            commands.append(f"color {color}, {target}")
        elif action.action == "background":
            color = action.value or ""
            if not _SAFE_COLOR.fullmatch(color):
                raise ConfigurationError("不支持的背景颜色")
            commands.append(f"bg_color {color}")
        elif action.action == "focus":
            commands.append(f"zoom {target}")
        elif action.action == "orient":
            commands.append(f"orient {target}")
        elif action.action == "center":
            commands.append(f"center {target}")
        elif action.action == "label":
            label = action.value or '"%s%s" % (resn, resi)'
            if "\n" in label or ";" in label:
                raise ConfigurationError("标签内容包含不允许的分隔符")
            commands.append(f"label ({target} and name CA), {label}")
        elif action.action == "unlabel":
            commands.append(f"unlabel {target}")
        elif action.action == "select":
            commands.append(f"select ed_selection, {target}")
        elif action.action == "deselect":
            commands.append("deselect")
    return validate_safe_pml("\n".join(commands))


def validate_common_viewer_actions(
    actions: tuple[ViewerAction, ...],
) -> tuple[ViewerAction, ...]:
    """Reject actions that cannot be replayed consistently in both viewers."""

    supported = {
        "representation",
        "color",
        "background",
        "focus",
        "orient",
        "center",
    }
    for action in actions:
        if action.action not in supported:
            raise ConfigurationError(
                f"公共助手动作 {action.action} 无法在 PyMOL 与 Mol* 中一致执行；"
                "残基编辑请使用 region-edit，专家标签/选择请使用仅 PyMOL 控制台"
            )
        if action.target.strip().lower() != "all":
            raise ConfigurationError(
                "公共显示动作首版只支持 target=all；明确残基请使用 region-edit"
            )
    compile_viewer_actions(actions)
    return actions


_CHATPYMOL_SYSTEM_PROMPT = """
你是 EasyDesign 中的 ChatPyMol 原生分子可视化协作助手。

你的任务：
1. 根据用户指令修改当前完整 PML 文档。
2. 保留无关的人工编辑，以及所有以 "# @easydesign" 开头的结构管理行。
3. 返回简短中文说明、修改摘要、对话标题和修改后的完整 PML。

规则：
- 只使用原生 PyMOL 命令。
- 优先使用可逆的显示、选择、颜色、标签、相机、测量和 set 命令。
- 禁止 Python、run、system、shell、quit、reinitialize、文件写入和网络加载。
- 不得编造上下文里不存在的对象名、链、残基、配体或科学事实。
- structure metadata 是唯一允许引用的对象、链和编号清单；异质分组不等于已确认配体。
- 如果用户要求不存在或不明确的链、残基或异质分子，说明限制并保持相关 PML 不变。
- 指令有歧义时，采用最小且有用的视觉修改。
- ed_region_A、ed_region_B、ed_region_C 是 EasyDesign 管理的可编辑区域 selection。
  只有用户明确给出残基并要求修改 A/B/C 时才可更新；表达式必须使用 metadata
  中真实的 author chain/residue 编号。
- 用户没有明确说“原始编号/auth/author/PDB 编号”时，用户输入的数字一律解释为
  界面显示的 label_seq_id。EasyDesign 会在 explicit_region_edit_intent 中提供已经
  校验的 label_seq_id 和对应 author selector；你必须逐字使用该 selector，不能自行
  改用或猜测 author 编号。
- “最佳区域”“预测 hotspot”等请求不得直接改写 ed_region_A/B/C；保持完整 PML
  不变并说明需要用户确认 SASA/ScanNet 计划。
- PML 必须保持可人工编辑、可导出。
- 只返回 JSON，不要使用 Markdown 代码块。

JSON 格式必须恰好为：
{"assistantMessage":"中文说明","summary":"简短中文摘要",
 "conversationTitle":"不超过18个字的对话标题","pml":"完整 PML"}
""".strip()


def _chatpymol_messages(
    *,
    user_text: str,
    context: dict[str, Any],
    history: tuple[InteractionMessage, ...],
    skills: tuple[PmlSkill, ...],
    previous_content: str | None = None,
    validation_error: str | None = None,
) -> list[dict[str, str]]:
    recent_history = [{"role": item.role, "content": item.content} for item in history[-10:]]
    messages: list[dict[str, str]] = [
        {
            "role": "system",
            "content": f"{_CHATPYMOL_SYSTEM_PROMPT}\n\n{render_pml_skills(skills)}",
        },
        *recent_history,
        {
            "role": "user",
            "content": (
                "当前工作区：\n"
                + json.dumps(context, ensure_ascii=False, separators=(",", ":"))
                + "\n\n用户要求：\n"
                + user_text
            ),
        },
    ]
    if previous_content is not None and validation_error is not None:
        messages.extend(
            [
                {"role": "assistant", "content": previous_content[:20_000]},
                {
                    "role": "user",
                    "content": (
                        "上一次响应未通过 EasyDesign 校验。"
                        "请只返回四字段 JSON；保留完整 PML 和所有 # @easydesign 管理行。"
                        f"\n校验错误：{validation_error[:4_000]}"
                    ),
                },
            ]
        )
    return messages


def _chatpymol_request_payload(
    *,
    model: str,
    user_text: str,
    context: dict[str, Any],
    history: tuple[InteractionMessage, ...],
    skills: tuple[PmlSkill, ...],
    previous_content: str | None = None,
    validation_error: str | None = None,
) -> dict[str, Any]:
    return {
        "model": model,
        "messages": _chatpymol_messages(
            user_text=user_text,
            context=context,
            history=history,
            skills=skills,
            previous_content=previous_content,
            validation_error=validation_error,
        ),
        "response_format": {"type": "json_object"},
        "temperature": 0.15,
    }


def _parse_chatpymol_edit(
    content: str,
    *,
    previous_pml: str,
    known_object_names: tuple[str, ...],
    known_chain_ids: tuple[str, ...],
) -> ChatPyMolEdit:
    cleaned = re.sub(r"^```(?:json)?\s*", "", content.strip(), flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    edit = ChatPyMolEdit.model_validate_json(cleaned)
    normalized = validate_scene_pml(
        edit.pml,
        previous_pml=previous_pml,
        known_object_names=known_object_names,
        known_chain_ids=known_chain_ids,
    )
    return edit.model_copy(update={"pml": normalized})


def request_assistant_pml_edit(
    *,
    secret: AssistantProviderSecret,
    user_text: str,
    context: dict[str, Any],
    history: tuple[InteractionMessage, ...],
    client: httpx.Client | None = None,
    previous_pml: str,
    known_object_names: tuple[str, ...] = (),
    known_chain_ids: tuple[str, ...] = (),
    edit_validator: Callable[[ChatPyMolEdit], ChatPyMolEdit] | None = None,
) -> tuple[ChatPyMolEdit, str | None, tuple[str, ...]]:
    """Call one provider using ChatPyMol's complete-PML request/response loop."""

    skills = select_pml_skills(user_text)
    own_client = client is None
    selected_client = client or httpx.Client(
        timeout=httpx.Timeout(60.0, connect=10.0, read=45.0),
        trust_env=False,
    )
    endpoint = secret.base_url
    if not endpoint.endswith("/chat/completions"):
        endpoint = f"{endpoint}/chat/completions"
    headers = {
        "Authorization": f"Bearer {secret.api_key}",
        "Content-Type": "application/json",
    }
    previous_content: str | None = None
    validation_error: str | None = None
    request_id: str | None = None
    try:
        for attempt in range(2):
            response = selected_client.post(
                endpoint,
                headers=headers,
                json=_chatpymol_request_payload(
                    model=secret.model,
                    user_text=user_text,
                    context=context,
                    history=history,
                    skills=skills,
                    previous_content=previous_content,
                    validation_error=validation_error,
                ),
            )
            response.raise_for_status()
            payload = response.json()
            request_id = (
                str(response.headers.get("x-request-id") or payload.get("id") or "") or None
            )
            content = _assistant_content_from_response(payload)
            try:
                edit = _parse_chatpymol_edit(
                    content,
                    previous_pml=previous_pml,
                    known_object_names=known_object_names,
                    known_chain_ids=known_chain_ids,
                )
                if edit_validator is not None:
                    edit = edit_validator(edit)
                return edit, request_id, tuple(skill.skill_id for skill in skills)
            except (ConfigurationError, json.JSONDecodeError, ValueError) as error:
                previous_content = content
                validation_error = str(error)
                if attempt == 0:
                    continue
                raise ConfigurationError(
                    f"{secret.provider} API 返回的完整 PML 未通过 EasyDesign 安全校验；"
                    "原场景未被修改。"
                ) from error
        raise ConfigurationError(f"{secret.provider} API 响应无法验证")
    except httpx.HTTPStatusError as error:
        raise ConfigurationError(
            f"{secret.provider} API 返回 HTTP {error.response.status_code}"
        ) from error
    except (httpx.HTTPError, json.JSONDecodeError, ValueError) as error:
        raise ConfigurationError(f"{secret.provider} API 响应无法验证") from error
    finally:
        if own_client:
            selected_client.close()


def _assistant_content_from_response(payload: dict[str, Any]) -> str:
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        raise ConfigurationError("模型 API 没有返回 choices")
    content = choices[0].get("message", {}).get("content")
    if not isinstance(content, str) or not content.strip():
        raise ConfigurationError("模型 API 返回了空内容")
    return content
