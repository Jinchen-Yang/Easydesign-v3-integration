"""Safe, project-local structure interaction sessions and model adapters.

The browser may render a verified structure and the assistant may propose
display or explicit region operations.  Neither component is allowed to
mutate the scientific Target Bundle or publish a Stage 02 decision directly.
"""

from __future__ import annotations

import json
import os
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlparse
from uuid import uuid4

import httpx
from pydantic import BaseModel, ConfigDict, Field, model_validator

from easydesign.core import ConfigurationError
from easydesign.orchestration.task_tracking import (
    atomic_dump_runtime_model,
    load_latest_runtime_model,
)

ProviderId = Literal["deepseek", "zhipu-glm"]
ProposalKind = Literal[
    "viewer-actions",
    "region-edit",
    "analysis-plan",
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

    operation: Literal["add", "remove", "toggle", "replace"]
    region_id: Literal["A", "B", "C"]
    numbering: Literal["label", "auth", "sequence", "uniprot"] = "label"
    chain: str | None = None
    residues: tuple[str, ...] = Field(min_length=1, max_length=10_000)


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


class AssistantProposal(BaseModel):
    """The only shape accepted from a remote language model."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    proposal_id: str = ""
    kind: ProposalKind
    explanation: str = Field(min_length=1, max_length=8_000)
    viewer_actions: tuple[ViewerAction, ...] = ()
    region_operations: tuple[RegionEditOperation, ...] = ()
    analysis_plan: ScientificAnalysisPlan | None = None

    @model_validator(mode="after")
    def match_kind(self) -> AssistantProposal:
        if self.kind == "viewer-actions" and not self.viewer_actions:
            raise ValueError("viewer-actions proposal 必须包含动作")
        if self.kind == "region-edit" and not self.region_operations:
            raise ValueError("region-edit proposal 必须包含明确残基")
        if self.kind == "analysis-plan" and self.analysis_plan is None:
            raise ValueError("analysis-plan proposal 必须包含计划")
        if self.kind == "explanation" and (
            self.viewer_actions or self.region_operations or self.analysis_plan is not None
        ):
            raise ValueError("explanation proposal 不能携带可执行操作")
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
    proposal: AssistantProposal | None = None


class PmlRevision(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    revision: int = Field(ge=1)
    pml: str = Field(max_length=1_000_000)
    source: Literal["viewer", "assistant", "expert-console"]
    created_at: datetime


class StructureInteractionSession(BaseModel):
    """Mutable product workflow represented by immutable full snapshots."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["0.1"] = "0.1"
    session_id: str
    project_id: str
    run_key: str
    stage_number: Literal[1, 2]
    target_structure_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    residue_mapping_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    selected_provider: ProviderId | None = None
    messages: tuple[InteractionMessage, ...] = ()
    pml_revisions: tuple[PmlRevision, ...] = ()
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


class StructureInteractionStore:
    """Project-local revision-only interaction storage."""

    def __init__(self, projects_root: Path) -> None:
        self.projects_root = projects_root.resolve()
        self.projects_root.mkdir(parents=True, exist_ok=True)

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
        roots = (
            self._project_root(project_id) / "interactive-sessions"
        ).glob("structure-session-*/session.json")
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
            if message.proposal is not None
            and message.proposal.proposal_id == proposal_id
        )
        if len(proposals) != 1:
            raise ConfigurationError("待应用的助手 proposal 不存在或不唯一")
        return proposals[0]

    def _publish(self, value: StructureInteractionSession) -> StructureInteractionSession:
        path = self._session_root(value.project_id, value.session_id) / "session.json"
        atomic_dump_runtime_model(value, path)
        return value

    def append_exchange(
        self,
        session_id: str,
        *,
        user_text: str,
        proposal: AssistantProposal,
        provider: ProviderId,
        model: str,
        request_id: str | None,
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

    def apply_proposal(
        self,
        session_id: str,
        *,
        proposal_id: str,
        pml: str | None = None,
        current_regions: dict[str, tuple[int, ...]] | None = None,
        source: Literal["viewer", "assistant", "expert-console"] = "assistant",
        updated_at: datetime | None = None,
    ) -> StructureInteractionSession:
        current = self.load(session_id)
        self.proposal(session_id, proposal_id)
        now = updated_at or datetime.now(tz=UTC)
        revisions = current.pml_revisions
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
        normalized_regions = current.current_regions
        if current_regions is not None:
            normalized_regions = normalize_regions(current_regions)
        return self._publish(
            current.model_copy(
                update={
                    "pml_revisions": revisions,
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
        validated = validate_safe_pml(pml)
        revision = PmlRevision(
            revision=len(current.pml_revisions) + 1,
            pml=validated,
            source=source,
            created_at=now,
        )
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


def _assistant_schema_prompt() -> str:
    return """
你是 EasyDesign 的结构显示助手。只输出一个 JSON object，禁止输出 Markdown。
你不能判断真实 hotspot、binding site 或科学优劣，也不能修改坐标、对象或文件。
允许的 kind:
1. viewer-actions: viewer_actions 非空，只做 representation/color/background/focus/orient/
   center/label/unlabel/select/deselect。
2. region-edit: 用户明确给出残基编号并要求加入/移出 A/B/C 时使用。
3. analysis-plan: 用户要求自动寻找、预测、比较或推荐区域时使用；methods 只能是
   sasa/scannet，requires_confirmation 必须为 true。
4. explanation: 只解释，不执行。
字段固定为 kind、explanation、viewer_actions、region_operations、analysis_plan。
不得产生任意 PML，不得把模型建议描述为科学验证结果。
""".strip()


def request_assistant_proposal(
    *,
    secret: AssistantProviderSecret,
    user_text: str,
    context: dict[str, Any],
    client: httpx.Client | None = None,
) -> tuple[AssistantProposal, str | None]:
    """Call one explicitly selected provider and validate its structured result."""

    own_client = client is None
    selected_client = client or httpx.Client(
        timeout=httpx.Timeout(60.0, connect=10.0, read=45.0)
    )
    endpoint = secret.base_url
    if not endpoint.endswith("/chat/completions"):
        endpoint = f"{endpoint}/chat/completions"
    request_payload = {
        "model": secret.model,
        "messages": [
            {"role": "system", "content": _assistant_schema_prompt()},
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "request": user_text,
                        "scene_context": context,
                    },
                    ensure_ascii=False,
                    separators=(",", ":"),
                ),
            },
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0,
    }
    try:
        response = selected_client.post(
            endpoint,
            headers={
                "Authorization": f"Bearer {secret.api_key}",
                "Content-Type": "application/json",
            },
            json=request_payload,
        )
        response.raise_for_status()
        payload = response.json()
        choices = payload.get("choices")
        if not isinstance(choices, list) or not choices:
            raise ConfigurationError("模型 API 没有返回 choices")
        content = choices[0].get("message", {}).get("content")
        if not isinstance(content, str) or not content.strip():
            raise ConfigurationError("模型 API 返回了空内容")
        proposal = AssistantProposal.model_validate_json(content)
        request_id = response.headers.get("x-request-id") or payload.get("id")
        return proposal, str(request_id) if request_id is not None else None
    except httpx.HTTPStatusError as error:
        raise ConfigurationError(
            f"{secret.provider} API 返回 HTTP {error.response.status_code}"
        ) from error
    except (httpx.HTTPError, json.JSONDecodeError, ValueError) as error:
        raise ConfigurationError(f"{secret.provider} API 响应无法验证") from error
    finally:
        if own_client:
            selected_client.close()
