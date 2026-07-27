"""StageManifest、RunManifest 与证据成熟度契约。"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .artifacts import ID_PATTERN, SHA256_PATTERN, ArtifactRef
from .attempts import Attempt, ExecutionStatus
from .errors import ManifestStateError, UndeclaredArtifactError
from .timestamps import normalize_aware_datetime


class StageId(StrEnum):
    TARGET_PREPARATION = "01-target-preparation"
    HOTSPOT_DISCOVERY = "02-hotspot-discovery"
    BOLTZGEN_CONFIGURATION = "03-boltzgen-configuration"
    PILOT_GENERATION = "04-pilot-generation"
    PILOT_FILTERING = "05-pilot-filtering"
    SCALE_GENERATION_AND_REFOLDING = "06-scale-generation-and-refolding"
    FINAL_FILTERING_AND_SELECTION = "07-final-filtering-and-selection"


class EvidenceStatus(StrEnum):
    """项目证据成熟度，与一次执行的运行状态分离。"""

    PLANNED = "planned"
    IMPLEMENTED = "implemented"
    SMOKE_VALIDATED = "smoke-validated"
    SCIENTIFICALLY_VALIDATED = "scientifically-validated"
    PRODUCTION_READY = "production-ready"


class CodeIdentitySource(StrEnum):
    """运行代码身份的来源；Git commit 与内容哈希不能互相冒充。"""

    GIT = "git"
    WORKING_TREE = "working-tree"
    INSTALLED_PACKAGE = "installed-package"


class CodeIdentity(BaseModel):
    """源码 checkout 或已安装 package 的可审计身份。"""

    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    distribution: str = Field(default="easydesign", pattern=ID_PATTERN)
    version: str = Field(min_length=1, max_length=64)
    source: CodeIdentitySource
    git_commit: str | None = Field(default=None, pattern=r"^[0-9a-f]{40}$")
    dirty: bool
    content_sha256: str | None = Field(default=None, pattern=SHA256_PATTERN)

    @model_validator(mode="after")
    def validate_identity(self) -> Self:
        if self.source is CodeIdentitySource.GIT:
            if self.git_commit is None or self.dirty:
                raise ValueError("clean Git identity 必须包含 commit 且 dirty=false")
        elif self.source is CodeIdentitySource.WORKING_TREE:
            if self.git_commit is None or not self.dirty or self.content_sha256 is None:
                raise ValueError(
                    "working-tree identity 必须包含基础 commit、dirty=true 和内容 SHA-256"
                )
        elif (
            self.git_commit is not None
            or self.dirty
            or self.content_sha256 is None
        ):
            raise ValueError(
                "installed-package identity 只能使用 package 内容 SHA-256"
            )
        return self


class RuntimeProfileRef(BaseModel):
    """不泄露机器路径的 runtime profile 身份。"""

    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    profile_id: str = Field(pattern=ID_PATTERN)
    sha256: str = Field(pattern=SHA256_PATTERN)


class WorkflowStateType(StrEnum):
    AWAITING_HUMAN_APPROVAL = "awaiting-human-approval"


class WorkflowState(BaseModel):
    """进程已退出但 run 仍等待显式输入的可恢复工作流状态。"""

    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    state: WorkflowStateType
    stage_id: StageId
    action: str = Field(pattern=ID_PATTERN)
    message: str = Field(min_length=1, max_length=4096)


def _validate_unique_artifacts(artifacts: tuple[ArtifactRef, ...], label: str) -> None:
    ids = [artifact.artifact_id for artifact in artifacts]
    if len(ids) != len(set(ids)):
        raise ValueError(f"{label} artifact_id 不能重复")


class StageManifest(BaseModel):
    """一个阶段已接受输入、输出和 attempt 历史的不可变快照。"""

    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    schema_version: str = Field(default="1.0", pattern=r"^[0-9]+\.[0-9]+$")
    stage_id: StageId
    contract_version: str = Field(pattern=r"^[0-9]+\.[0-9]+$")
    status: ExecutionStatus
    created_at: datetime
    completed_at: datetime | None = None
    input_artifacts: tuple[ArtifactRef, ...] = ()
    output_artifacts: tuple[ArtifactRef, ...] = ()
    attempts: tuple[Attempt, ...] = ()
    selected_attempt_id: str | None = Field(default=None, pattern=r"^attempt-[0-9]{4,}$")
    warnings: tuple[str, ...] = ()

    @field_validator("created_at", "completed_at")
    @classmethod
    def normalize_datetime(cls, value: datetime | None) -> datetime | None:
        return None if value is None else normalize_aware_datetime(value)

    @model_validator(mode="after")
    def validate_manifest(self) -> Self:
        _validate_unique_artifacts(self.input_artifacts, "input")
        _validate_unique_artifacts(self.output_artifacts, "output")
        all_ids = [
            artifact.artifact_id
            for artifact in self.input_artifacts + self.output_artifacts
        ]
        if len(all_ids) != len(set(all_ids)):
            raise ValueError("同一 StageManifest 的 input/output artifact_id 不能重复")

        attempt_ids = [attempt.attempt_id for attempt in self.attempts]
        if len(attempt_ids) != len(set(attempt_ids)):
            raise ValueError("attempt_id 不能重复")
        attempts_by_id = {attempt.attempt_id: attempt for attempt in self.attempts}

        if self.status.is_terminal:
            if self.completed_at is None:
                raise ValueError("终态 stage 必须有 completed_at")
            if self.completed_at < self.created_at:
                raise ValueError("stage 完成时间不能早于创建时间")
        elif self.completed_at is not None:
            raise ValueError("非终态 stage 不能有 completed_at")

        selected = None
        if self.selected_attempt_id is not None:
            selected = next(
                (
                    attempt
                    for attempt in self.attempts
                    if attempt.attempt_id == self.selected_attempt_id
                ),
                None,
            )
            if selected is None:
                raise ValueError("selected_attempt_id 必须引用已声明 attempt")

        if self.status is ExecutionStatus.SUCCEEDED:
            if selected is None or selected.status is not ExecutionStatus.SUCCEEDED:
                raise ValueError("succeeded stage 必须选择一个 succeeded attempt")
            if not self.output_artifacts:
                raise ValueError("succeeded stage 必须声明至少一个 output artifact")
        elif self.selected_attempt_id is not None:
            raise ValueError("只有 succeeded stage 可以选择 attempt")

        if self.status is not ExecutionStatus.SUCCEEDED and self.output_artifacts:
            raise ValueError("只有 succeeded stage 可以发布 output artifact")

        expected_stage = str(self.stage_id)
        for artifact in self.output_artifacts:
            if artifact.producer_stage != expected_stage:
                raise ValueError(
                    f"output artifact 的 producer_stage 必须是 {expected_stage}"
                )
            producer_attempt = attempts_by_id.get(artifact.producer_attempt or "")
            if producer_attempt is None:
                raise ValueError("output artifact 必须引用本 manifest 声明的 attempt")
            if producer_attempt.status is not ExecutionStatus.SUCCEEDED:
                raise ValueError("output artifact 必须由 succeeded attempt 产生")
            if artifact.producer_attempt != self.selected_attempt_id:
                raise ValueError("output artifact 必须来自 selected attempt")
        return self

    def require_input(self, artifact_id: str) -> ArtifactRef:
        """返回声明的输入；未声明时明确失败。"""

        for artifact in self.input_artifacts:
            if artifact.artifact_id == artifact_id:
                return artifact
        raise UndeclaredArtifactError(
            f"{self.stage_id} 未声明 input artifact: {artifact_id}"
        )

    def require_output(self, artifact_id: str) -> ArtifactRef:
        """返回声明的输出；未声明时明确失败。"""

        for artifact in self.output_artifacts:
            if artifact.artifact_id == artifact_id:
                return artifact
        raise UndeclaredArtifactError(
            f"{self.stage_id} 未声明 output artifact: {artifact_id}"
        )

    def validate_inputs_declared_by(
        self,
        upstream_manifests: tuple[StageManifest, ...],
    ) -> None:
        """验证所有带 producer 的输入与上游正式输出完全一致。"""

        stage_ids = [manifest.stage_id for manifest in upstream_manifests]
        if len(stage_ids) != len(set(stage_ids)):
            raise UndeclaredArtifactError("同一上游 stage 不能提供多个 manifest")

        current_number = int(str(self.stage_id).split("-", maxsplit=1)[0])
        for manifest in upstream_manifests:
            upstream_number = int(str(manifest.stage_id).split("-", maxsplit=1)[0])
            if upstream_number >= current_number:
                raise UndeclaredArtifactError(
                    f"{manifest.stage_id} 不是 {self.stage_id} 的上游阶段"
                )
            if manifest.status is not ExecutionStatus.SUCCEEDED:
                raise UndeclaredArtifactError(
                    f"{manifest.stage_id} 尚未成功，不能提供正式 artifact"
                )

        declared = {
            (str(manifest.stage_id), artifact.artifact_id): artifact
            for manifest in upstream_manifests
            for artifact in manifest.output_artifacts
        }
        for artifact in self.input_artifacts:
            if artifact.producer_stage is None:
                continue
            key = (artifact.producer_stage, artifact.artifact_id)
            upstream = declared.get(key)
            if upstream is None:
                raise UndeclaredArtifactError(
                    f"{self.stage_id} 输入未由上游声明: "
                    f"producer={artifact.producer_stage}, artifact={artifact.artifact_id}"
                )
            if upstream != artifact:
                raise UndeclaredArtifactError(
                    f"{self.stage_id} 输入与上游声明不一致: artifact={artifact.artifact_id}"
                )


class RunManifest(BaseModel):
    """一次完整七阶段 run 的版本化不可变快照。"""

    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    schema_version: str = Field(default="1.0", pattern=r"^[0-9]+\.[0-9]+$")
    revision: int = Field(ge=1)
    previous_manifest_sha256: str | None = Field(default=None, pattern=SHA256_PATTERN)
    project_id: str = Field(pattern=ID_PATTERN)
    run_id: str = Field(pattern=ID_PATTERN)
    easydesign_version: str = Field(min_length=1, max_length=64)
    code_commit: str | None = Field(default=None, pattern=r"^[0-9a-f]{7,40}$")
    code_identity: CodeIdentity | None = None
    runtime_profile: RuntimeProfileRef | None = None
    workflow_state: WorkflowState | None = None
    status: ExecutionStatus
    evidence_status: EvidenceStatus
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None = None
    config_snapshot: ArtifactRef
    stage_manifest_refs: tuple[ArtifactRef, ...] = ()

    @field_validator("created_at", "updated_at", "completed_at")
    @classmethod
    def normalize_datetime(cls, value: datetime | None) -> datetime | None:
        return None if value is None else normalize_aware_datetime(value)

    @model_validator(mode="after")
    def validate_manifest(self) -> Self:
        if self.schema_version == "1.0":
            if self.code_commit is None:
                raise ValueError("RunManifest 1.0 必须包含 code_commit")
            if (
                self.code_identity is not None
                or self.runtime_profile is not None
                or self.workflow_state is not None
            ):
                raise ValueError(
                    "RunManifest 1.0 不支持结构化代码、profile 或 workflow 身份"
                )
        elif self.schema_version in {"1.1", "1.2"}:
            if self.code_identity is None:
                raise ValueError(
                    f"RunManifest {self.schema_version} 必须包含 code_identity"
                )
            if self.code_commit is not None:
                raise ValueError(
                    f"RunManifest {self.schema_version} "
                    "不得把 code_identity 重复写成 code_commit"
                )
            if self.schema_version == "1.1" and self.workflow_state is not None:
                raise ValueError("RunManifest 1.1 不支持 workflow_state")
        else:
            raise ValueError(f"不支持的 RunManifest schema_version: {self.schema_version}")
        if self.revision == 1 and self.previous_manifest_sha256 is not None:
            raise ValueError("revision 1 不能声明 previous manifest")
        if self.revision > 1 and self.previous_manifest_sha256 is None:
            raise ValueError("revision > 1 必须声明 previous manifest SHA-256")
        if self.updated_at < self.created_at:
            raise ValueError("updated_at 不能早于 created_at")

        if self.status.is_terminal:
            if self.completed_at is None:
                raise ValueError("终态 run 必须有 completed_at")
            if self.completed_at < self.created_at:
                raise ValueError("run 完成时间不能早于创建时间")
        elif self.completed_at is not None:
            raise ValueError("非终态 run 不能有 completed_at")
        if (
            self.workflow_state is not None
            and self.status is not ExecutionStatus.RUNNING
        ):
            raise ValueError("workflow_state 只能出现在 running RunManifest")

        stages = [reference.producer_stage for reference in self.stage_manifest_refs]
        if any(stage is None for stage in stages):
            raise ValueError("stage manifest ref 必须声明 producer_stage")
        if len(stages) != len(set(stages)):
            raise ValueError("每个 stage 只能有一个当前 manifest ref")
        return self

    def next_revision(
        self,
        *,
        updated_at: datetime,
        status: ExecutionStatus | None = None,
        completed_at: datetime | None = None,
        stage_manifest_refs: tuple[ArtifactRef, ...] | None = None,
        workflow_state: WorkflowState | None = None,
        clear_workflow_state: bool = False,
    ) -> Self:
        """以当前 manifest hash 为前驱创建经过完整校验的新快照。"""

        from .serialization import canonical_model_sha256

        if self.status.is_terminal:
            raise ManifestStateError("终态 RunManifest 不能再创建后续 revision")
        if updated_at <= self.updated_at:
            raise ManifestStateError("新 revision 的 updated_at 必须晚于当前 revision")
        next_status = self.status if status is None else status
        if self.status is ExecutionStatus.RUNNING and next_status is ExecutionStatus.PENDING:
            raise ManifestStateError("RunManifest 状态不能从 running 回退到 pending")
        if workflow_state is not None and clear_workflow_state:
            raise ManifestStateError(
                "workflow_state 与 clear_workflow_state 不能同时设置"
            )
        next_workflow_state = (
            None
            if clear_workflow_state
            else (
                self.workflow_state
                if workflow_state is None
                else workflow_state
            )
        )

        payload = self.model_dump(mode="python")
        payload.update(
            {
                "revision": self.revision + 1,
                "previous_manifest_sha256": canonical_model_sha256(self),
                "updated_at": updated_at,
                "status": next_status,
                "completed_at": completed_at,
                "stage_manifest_refs": (
                    self.stage_manifest_refs
                    if stage_manifest_refs is None
                    else stage_manifest_refs
                ),
                "workflow_state": next_workflow_state,
            }
        )
        return self.__class__.model_validate(payload)

    def continue_after_success(
        self,
        *,
        updated_at: datetime,
        config_snapshot: ArtifactRef,
        easydesign_version: str,
        code_identity: CodeIdentity,
        runtime_profile: RuntimeProfileRef,
    ) -> Self:
        """在保留终态快照的前提下，为下一 Stage 重新开启同一个 run。

        只有成功终态可以继续。失败、科学停止或等待人工动作必须先使用各自的恢复/
        决策协议，不能借本方法绕过。
        """

        from .serialization import canonical_model_sha256

        if self.status is not ExecutionStatus.SUCCEEDED:
            raise ManifestStateError("只有 succeeded RunManifest 可以继续下一 Stage")
        if self.schema_version not in {"1.1", "1.2"}:
            raise ManifestStateError("旧 RunManifest schema 不支持同 run 阶段延续")
        if updated_at <= self.updated_at:
            raise ManifestStateError("续跑 revision 的 updated_at 必须晚于当前 revision")
        payload = self.model_dump(mode="python")
        payload.update(
            {
                "revision": self.revision + 1,
                "previous_manifest_sha256": canonical_model_sha256(self),
                "updated_at": updated_at,
                "status": ExecutionStatus.RUNNING,
                "completed_at": None,
                "config_snapshot": config_snapshot,
                "easydesign_version": easydesign_version,
                "code_commit": None,
                "code_identity": code_identity,
                "runtime_profile": runtime_profile,
                "workflow_state": None,
            }
        )
        return self.__class__.model_validate(payload)
