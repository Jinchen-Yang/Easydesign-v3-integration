"""一次实验一个目录的 Run Workspace 创建和可再生索引。"""

from __future__ import annotations

import json
import re
import shutil
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from easydesign.backends.structure_prediction import StructurePredictionRequest
from easydesign.backends.structure_prediction.contracts import MsaMode
from easydesign.backends.target_sources import NormalizedProteinSequence
from easydesign.core import (
    ArtifactRef,
    CodeIdentity,
    EvidenceStatus,
    ExecutionStatus,
    ManifestStateError,
    RunManifest,
    RuntimeProfileRef,
    StageId,
    dump_model,
    load_model,
)
from easydesign.core.artifacts import ID_PATTERN
from easydesign.core.timestamps import normalize_aware_datetime
from easydesign.safe_writes import (
    append_pointer_revision,
    quarantine_if_workspace_path,
    read_last_text_line,
)

from .config import (
    EasyDesignRunConfig,
    LoadedPseRunConfig,
    LoadedRunConfig,
    LoadedSequenceRunConfig,
    ResolvedProtenixMsaProviderConfig,
    TargetInputFormat,
    load_run_config,
)
from .task_tracking import atomic_dump_runtime_model, load_latest_runtime_model


class PredictionInputWriter(Protocol):
    model_name: str

    def write_input(
        self,
        request: StructurePredictionRequest,
        path: Path,
    ) -> Path: ...


class PseRequestWriter(Protocol):
    backend_name: str

    def build_request(
        self,
        *,
        run_root: Path,
        source_path: Path,
        target_id: str,
    ) -> BaseModel: ...

    def write_request(self, request: BaseModel, path: Path) -> Path: ...


class ResolvedRunConfig(BaseModel):
    """写入 run 的完全解析配置，不包含站点专属后端路径。"""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: str = "0.7"
    project_id: str = Field(pattern=ID_PATTERN)
    run_id: str = Field(pattern=ID_PATTERN)
    user_config: EasyDesignRunConfig
    detected_input_format: TargetInputFormat
    input_snapshot: ArtifactRef
    target: NormalizedProteinSequence | None = None
    prediction_request: StructurePredictionRequest | None = None
    msa_execution_plan: tuple[ResolvedProtenixMsaProviderConfig, ...] = ()
    precomputed_msa_snapshot: ArtifactRef | None = None
    stop_after_stage: int = Field(ge=1, le=7)
    runtime_profile: RuntimeProfileRef | None = None

    @model_validator(mode="after")
    def validate_input_branch(self) -> Self:
        if self.schema_version == "0.3" and self.runtime_profile is not None:
            raise ValueError("resolved config 0.3 不支持 runtime_profile")
        if self.schema_version not in {
            "0.2",
            "0.3",
            "0.4",
            "0.5",
            "0.6",
            "0.7",
        }:
            raise ValueError(f"不支持的 resolved config schema: {self.schema_version}")
        is_sequence = self.detected_input_format in {
            TargetInputFormat.SEQUENCE,
            TargetInputFormat.FASTA,
        }
        if is_sequence and (self.target is None or self.prediction_request is None):
            raise ValueError("sequence/FASTA resolved config 必须包含规范序列和预测请求")
        if is_sequence and self.schema_version != "0.2":
            assert self.prediction_request is not None
            if self.prediction_request.msa_mode is MsaMode.REMOTE:
                if not self.msa_execution_plan or self.precomputed_msa_snapshot is not None:
                    raise ValueError("remote MSA 必须且只能包含 execution plan")
            elif self.prediction_request.msa_mode is MsaMode.PRECOMPUTED:
                if self.msa_execution_plan or self.precomputed_msa_snapshot is None:
                    raise ValueError("precomputed MSA 必须且只能包含输入 snapshot")
        if not is_sequence and (self.target is not None or self.prediction_request is not None):
            raise ValueError("非 sequence resolved config 不得伪造预测请求")
        if not is_sequence and self.msa_execution_plan:
            raise ValueError("非 sequence resolved config 不得声明 MSA execution plan")
        if (
            not is_sequence
            and self.precomputed_msa_snapshot is not None
            and self.detected_input_format
            not in {TargetInputFormat.UNIPROT, TargetInputFormat.UNIPROT_SEARCH}
        ):
            raise ValueError("该非 sequence source 不得声明 precomputed MSA")
        return self


def load_resolved_run_config(run_root: Path) -> tuple[ResolvedRunConfig, Path]:
    """读取当前解析配置；兼容没有 CURRENT 指针的历史 run。"""

    root = run_root.resolve()
    config_root = root / "config-snapshot"
    pointer = config_root / "CURRENT"
    if pointer.is_file():
        relative = read_last_text_line(pointer)
        if not relative:
            raise ManifestStateError("config-snapshot/CURRENT 不能为空")
        path = (config_root / relative).resolve()
        if not path.is_relative_to(config_root.resolve()):
            raise ManifestStateError("config-snapshot/CURRENT 逃逸 config-snapshot")
    else:
        path = config_root / "resolved-config.json"
    if not path.is_file():
        raise ManifestStateError(f"当前 resolved config 不存在: {path}")
    return load_model(path, ResolvedRunConfig), path


class RunIndexEntry(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    category: str = Field(pattern=ID_PATTERN)
    path: str = Field(min_length=1)
    layout_version: str = Field(min_length=1, max_length=32)
    status: str = Field(min_length=1, max_length=64)
    project_id: str | None = Field(default=None, pattern=ID_PATTERN)
    run_id: str | None = Field(default=None, pattern=ID_PATTERN)
    is_project_primary: bool = False
    notes: tuple[str, ...] = ()


class RunIndex(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: str = "0.1"
    generated_at: datetime
    entries: tuple[RunIndexEntry, ...]

    @field_validator("generated_at")
    @classmethod
    def normalize_datetime(cls, value: datetime) -> datetime:
        return normalize_aware_datetime(value)

    @model_validator(mode="after")
    def validate_unique_paths(self) -> Self:
        paths = [entry.path for entry in self.entries]
        if len(paths) != len(set(paths)):
            raise ValueError("run-index path 不能重复")
        primary_projects = [
            (entry.category, entry.project_id)
            for entry in self.entries
            if entry.is_project_primary
        ]
        if len(primary_projects) != len(set(primary_projects)):
            raise ValueError("同一分类中的项目只能指定一个主展示运行")
        for entry in self.entries:
            if entry.is_project_primary and (
                entry.category != "project-run"
                or entry.project_id is None
                or entry.run_id is None
            ):
                raise ValueError("主展示运行必须是含 project_id/run_id 的 project-run")
        return self


class ProjectRunNavigation(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    run_id: str = Field(pattern=ID_PATTERN)
    relative_path: str = Field(min_length=1)
    status: str = Field(min_length=1, max_length=64)
    is_primary: bool = False


class ProjectNavigation(BaseModel):
    """项目目录中的可再生导航投影，不属于科学证据。"""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: str = "0.1"
    project_id: str = Field(pattern=ID_PATTERN)
    primary_run_id: str | None = Field(default=None, pattern=ID_PATTERN)
    generated_at: datetime
    runs: tuple[ProjectRunNavigation, ...]

    @field_validator("generated_at")
    @classmethod
    def normalize_generated_at(cls, value: datetime) -> datetime:
        return normalize_aware_datetime(value)


@dataclass(frozen=True, slots=True)
class RunWorkspace:
    runs_root: Path
    run_root: Path
    project_id: str
    run_id: str
    config_snapshot: Path
    input_snapshot: Path
    resolved_config: Path
    run_manifest: Path
    latest_manifest_pointer: Path

    def stage_root(self, stage_id: StageId) -> Path:
        return self.run_root / str(stage_id)

    def attempt_root(self, stage_id: StageId, attempt_id: str) -> Path:
        return self.stage_root(stage_id) / attempt_id


@dataclass(frozen=True, slots=True)
class PreparedRun:
    loaded_config: LoadedRunConfig
    workspace: RunWorkspace


@dataclass(frozen=True, slots=True)
class PreparedSequenceRun:
    loaded_config: LoadedSequenceRunConfig
    workspace: RunWorkspace
    protenix_input: Path
    precomputed_msa: Path | None = None


@dataclass(frozen=True, slots=True)
class PreparedPseRun:
    loaded_config: LoadedPseRunConfig
    workspace: RunWorkspace
    pse_request: Path


def _exclusive_copy(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        with source.open("rb") as input_handle, destination.open("xb") as output_handle:
            shutil.copyfileobj(input_handle, output_handle)
    except FileExistsError as error:
        raise ManifestStateError(f"不可覆盖 run snapshot: {destination}") from error


def _exclusive_text(text: str, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        with destination.open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
    except FileExistsError as error:
        raise ManifestStateError(f"不可覆盖 run 文件: {destination}") from error


def _atomic_replace_json(model: BaseModel, path: Path) -> None:
    atomic_dump_runtime_model(model, path)


def _atomic_replace_text(text: str, path: Path) -> None:
    append_pointer_revision(path, text)


def _sync_project_navigation_files(runs_root: Path, index: RunIndex) -> None:
    """从 run-index 生成 PROJECT.json/PRIMARY，并移除归档后的导航空壳。"""

    root = runs_root.resolve()
    active: dict[str, list[RunIndexEntry]] = {}
    for entry in index.entries:
        if (
            entry.category != "project-run"
            or entry.project_id is None
            or entry.run_id is None
        ):
            continue
        parts = Path(entry.path).parts
        if len(parts) < 2 or parts[0] != entry.project_id:
            continue
        active.setdefault(entry.project_id, []).append(entry)

    for project_id, entries in active.items():
        project_root = root / project_id
        if project_root.is_symlink():
            raise ManifestStateError(f"项目目录不能是符号链接: {project_root}")
        project_root.mkdir(parents=True, exist_ok=True)
        ordered = sorted(entries, key=lambda entry: (entry.run_id or "", entry.path))
        primary = next((entry.run_id for entry in ordered if entry.is_project_primary), None)
        navigation = ProjectNavigation(
            project_id=project_id,
            primary_run_id=primary,
            generated_at=index.generated_at,
            runs=tuple(
                ProjectRunNavigation(
                    run_id=entry.run_id or "",
                    relative_path=entry.path,
                    status=entry.status,
                    is_primary=entry.is_project_primary,
                )
                for entry in ordered
            ),
        )
        _atomic_replace_json(navigation, project_root / "PROJECT.json")
        primary_path = project_root / "PRIMARY"
        if primary is None:
            quarantine_if_workspace_path(
                primary_path,
                operation="project-navigation",
                reason="项目当前没有 primary run；保留旧 pointer 供审计",
            )
        else:
            _atomic_replace_text(primary + "\n", primary_path)

    if not root.is_dir():
        return
    for project_root in root.iterdir():
        if (
            not project_root.is_dir()
            or project_root.is_symlink()
            or project_root.name.startswith("_")
            or project_root.name in active
        ):
            continue
        project_file = project_root / "PROJECT.json"
        if project_file.is_file():
            quarantine_if_workspace_path(
                project_root,
                operation="project-navigation-shell",
                reason="项目已不在活跃 run-index；导航空壳移入隔离区",
            )


def upsert_run_index_entries(
    runs_root: Path,
    entries: tuple[RunIndexEntry, ...],
    *,
    generated_at: datetime,
) -> Path:
    """更新可再生目录索引；索引不是科学 artifact。"""

    index_path = runs_root / "run-index.json"
    existing: tuple[RunIndexEntry, ...] = ()
    if index_path.is_file():
        existing = load_latest_runtime_model(index_path, RunIndex).entries
    by_path = {entry.path: entry for entry in existing}
    for entry in entries:
        previous = by_path.get(entry.path)
        if previous is not None and previous.is_project_primary:
            entry = entry.model_copy(update={"is_project_primary": True})
        by_path[entry.path] = entry
    index = RunIndex(
        generated_at=generated_at,
        entries=tuple(by_path[path] for path in sorted(by_path)),
    )
    _atomic_replace_json(index, index_path)
    _sync_project_navigation_files(runs_root, index)
    return index_path


def replace_run_index_entries(
    runs_root: Path,
    entries: tuple[RunIndexEntry, ...],
    *,
    generated_at: datetime,
) -> Path:
    """原子替换可再生运行索引，用于归档等需要改变路径的受控迁移。"""

    index_path = runs_root / "run-index.json"
    index = RunIndex(
        generated_at=generated_at,
        entries=tuple(sorted(entries, key=lambda entry: entry.path)),
    )
    _atomic_replace_json(index, index_path)
    _sync_project_navigation_files(runs_root, index)
    return index_path


def _generated_run_id(created_at: datetime) -> str:
    utc = normalize_aware_datetime(created_at)
    return utc.strftime("%Y%m%dt%H%M%Sz").lower()


def _validate_run_id(run_id: str) -> None:
    if re.fullmatch(ID_PATTERN, run_id) is None:
        raise ManifestStateError(f"run_id 不符合稳定 slug 规则: {run_id}")


def _initialize_workspace(
    *,
    loaded: LoadedRunConfig,
    runs_root: Path,
    easydesign_version: str,
    code_commit: str | None,
    code_identity: CodeIdentity | None,
    runtime_profile: RuntimeProfileRef | None,
    selected_run_id: str,
    timestamp: datetime,
    prepare_attempt_input: Callable[[Path, Path], Path | None] | None,
    index_note: str,
) -> tuple[RunWorkspace, Path | None]:
    _validate_run_id(selected_run_id)
    if (code_commit is None) == (code_identity is None):
        raise ManifestStateError("code_commit 与 code_identity 必须且只能提供一个")

    root = runs_root.resolve()
    project_root = root / loaded.config.project_id
    final_root = project_root / selected_run_id
    project_root.mkdir(parents=True, exist_ok=True)
    if final_root.exists():
        raise ManifestStateError(f"run 已存在，不能覆盖: {final_root}")

    staging = Path(
        tempfile.mkdtemp(
            prefix=f".{selected_run_id}.creating-",
            dir=project_root,
        )
    )
    try:
        config_snapshot = staging / "config-snapshot" / "easydesign.yaml"
        input_snapshot = (
            staging / "input-snapshot" / loaded.source_path.name
            if loaded.source_path is not None
            else staging / "input-snapshot" / "target-source.json"
        )
        _exclusive_copy(loaded.config_path, config_snapshot)
        if loaded.source_path is None:
            _exclusive_text(
                json.dumps(
                    loaded.config.stage01.target.source.model_dump(mode="json"),
                    ensure_ascii=False,
                    indent=2,
                    sort_keys=True,
                )
                + "\n",
                input_snapshot,
            )
        else:
            _exclusive_copy(loaded.source_path, input_snapshot)

        config_ref = ArtifactRef.from_file(
            run_root=staging,
            relative_path="config-snapshot/easydesign.yaml",
            artifact_id="run-config",
            role="user-config-snapshot",
            file_format="yaml",
        )
        input_relative = input_snapshot.relative_to(staging).as_posix()
        input_ref = ArtifactRef.from_file(
            run_root=staging,
            relative_path=input_relative,
            artifact_id="target-source",
            role="target-source-snapshot",
            file_format=str(loaded.detected_format),
        )
        precomputed_msa_ref: ArtifactRef | None = None
        loaded_precomputed_msa = getattr(loaded, "precomputed_msa_path", None)
        if loaded_precomputed_msa is not None:
            precomputed_snapshot = staging / "input-snapshot" / "target-msa.a3m"
            _exclusive_copy(loaded_precomputed_msa, precomputed_snapshot)
            precomputed_msa_ref = ArtifactRef.from_file(
                run_root=staging,
                relative_path=precomputed_snapshot.relative_to(staging).as_posix(),
                artifact_id="precomputed-msa-source",
                role="msa-input-snapshot",
                file_format="a3m",
            )
        resolved = ResolvedRunConfig(
            schema_version="0.7",
            project_id=loaded.config.project_id,
            run_id=selected_run_id,
            user_config=loaded.config,
            detected_input_format=loaded.detected_format,
            input_snapshot=input_ref,
            target=loaded.target if isinstance(loaded, LoadedSequenceRunConfig) else None,
            prediction_request=(
                loaded.prediction_request
                if isinstance(loaded, LoadedSequenceRunConfig)
                else None
            ),
            msa_execution_plan=(
                loaded.msa_execution_plan
                if isinstance(loaded, LoadedSequenceRunConfig)
                else ()
            ),
            precomputed_msa_snapshot=precomputed_msa_ref,
            stop_after_stage=loaded.config.workflow.stop_after_stage,
            runtime_profile=runtime_profile,
        )
        resolved_path = staging / "config-snapshot" / "resolved-config.json"
        dump_model(resolved, resolved_path)
        _exclusive_text("resolved-config.json\n", staging / "config-snapshot" / "CURRENT")

        manifest = RunManifest(
            schema_version="1.2" if code_identity is not None else "1.0",
            revision=1,
            project_id=loaded.config.project_id,
            run_id=selected_run_id,
            easydesign_version=easydesign_version,
            code_commit=code_commit,
            code_identity=code_identity,
            runtime_profile=runtime_profile,
            status=ExecutionStatus.PENDING,
            evidence_status=EvidenceStatus.IMPLEMENTED,
            created_at=timestamp,
            updated_at=timestamp,
            config_snapshot=config_ref,
        )
        manifest_path = staging / "manifests" / "run-manifest.v0001.json"
        dump_model(manifest, manifest_path)
        latest_pointer = staging / "manifests" / "LATEST"
        _exclusive_text("run-manifest.v0001.json\n", latest_pointer)
        prepared_input = (
            None
            if prepare_attempt_input is None
            else prepare_attempt_input(staging, input_snapshot)
        )
        prepared_relative = (
            None
            if prepared_input is None
            else prepared_input.relative_to(staging)
        )
        staging.rename(final_root)
    except Exception:
        if staging.exists():
            quarantine_if_workspace_path(
                staging,
                operation="initialize-run",
                reason="run workspace 创建失败",
            )
        raise

    workspace = RunWorkspace(
        runs_root=root,
        run_root=final_root,
        project_id=loaded.config.project_id,
        run_id=selected_run_id,
        config_snapshot=final_root / "config-snapshot" / "easydesign.yaml",
        input_snapshot=(
            final_root / "input-snapshot" / loaded.source_path.name
            if loaded.source_path is not None
            else final_root / "input-snapshot" / "target-source.json"
        ),
        resolved_config=final_root / "config-snapshot" / "resolved-config.json",
        run_manifest=final_root / "manifests" / "run-manifest.v0001.json",
        latest_manifest_pointer=final_root / "manifests" / "LATEST",
    )
    upsert_run_index_entries(
        root,
        (
            RunIndexEntry(
                category="project-run",
                path=final_root.relative_to(root).as_posix(),
                layout_version="1",
                status="pending",
                project_id=workspace.project_id,
                run_id=workspace.run_id,
                notes=(index_note,),
            ),
        ),
        generated_at=timestamp,
    )
    final_prepared_input = (
        None
        if prepared_relative is None
        else workspace.run_root / prepared_relative
    )
    return workspace, final_prepared_input


def initialize_run_workspace(
    *,
    config_path: Path,
    runs_root: Path,
    easydesign_version: str,
    code_commit: str | None = None,
    code_identity: CodeIdentity | None = None,
    runtime_profile: RuntimeProfileRef | None = None,
    run_id: str | None = None,
    created_at: datetime | None = None,
) -> PreparedRun:
    """创建与 target 类型无关的 run 骨架；不生成任何 backend 私有输入。"""

    loaded = load_run_config(config_path)
    timestamp = datetime.now(UTC) if created_at is None else normalize_aware_datetime(created_at)
    selected_run_id = _generated_run_id(timestamp) if run_id is None else run_id
    workspace, prepared_input = _initialize_workspace(
        loaded=loaded,
        runs_root=runs_root,
        code_commit=code_commit,
        code_identity=code_identity,
        runtime_profile=runtime_profile,
        easydesign_version=easydesign_version,
        selected_run_id=selected_run_id,
        timestamp=timestamp,
        prepare_attempt_input=None,
        index_note="Run workspace initialized; Stage 01 input not prepared.",
    )
    assert prepared_input is None
    return PreparedRun(loaded_config=loaded, workspace=workspace)


def initialize_sequence_run(
    *,
    config_path: Path,
    runs_root: Path,
    input_writer: PredictionInputWriter,
    easydesign_version: str,
    code_commit: str | None = None,
    code_identity: CodeIdentity | None = None,
    runtime_profile: RuntimeProfileRef | None = None,
    run_id: str | None = None,
    created_at: datetime | None = None,
) -> PreparedSequenceRun:
    """从 sequence/FASTA 用户 YAML 创建 run 和 Protenix attempt input。"""

    loaded = load_run_config(config_path)
    if not isinstance(loaded, LoadedSequenceRunConfig):
        raise ManifestStateError(
            f"initialize_sequence_run 只接受 sequence/FASTA，实际为 {loaded.detected_format}"
        )
    prediction_config = loaded.config.structure_prediction
    assert prediction_config is not None
    if input_writer.model_name != prediction_config.backend:
        raise ManifestStateError(
            "配置 backend 与输入 writer 不一致: "
            f"config={prediction_config.backend}, writer={input_writer.model_name}"
        )
    timestamp = datetime.now(UTC) if created_at is None else normalize_aware_datetime(created_at)
    selected_run_id = _generated_run_id(timestamp) if run_id is None else run_id

    def prepare(staging: Path, _: Path) -> Path:
        path = (
            staging
            / str(StageId.TARGET_PREPARATION)
            / "attempt-0001"
            / "inputs"
            / "protenix-input.json"
        )
        return input_writer.write_input(loaded.prediction_request, path)

    workspace, prepared_input = _initialize_workspace(
        loaded=loaded,
        runs_root=runs_root,
        code_commit=code_commit,
        code_identity=code_identity,
        runtime_profile=runtime_profile,
        easydesign_version=easydesign_version,
        selected_run_id=selected_run_id,
        timestamp=timestamp,
        prepare_attempt_input=prepare,
        index_note="Stage 01 sequence input prepared; backend execution not started.",
    )
    assert prepared_input is not None
    return PreparedSequenceRun(
        loaded_config=loaded,
        workspace=workspace,
        protenix_input=prepared_input,
        precomputed_msa=(
            workspace.run_root / "input-snapshot" / "target-msa.a3m"
            if loaded.precomputed_msa_path is not None
            else None
        ),
    )


def initialize_pse_run(
    *,
    config_path: Path,
    runs_root: Path,
    request_writer: PseRequestWriter,
    easydesign_version: str,
    code_commit: str | None = None,
    code_identity: CodeIdentity | None = None,
    runtime_profile: RuntimeProfileRef | None = None,
    run_id: str | None = None,
    created_at: datetime | None = None,
) -> PreparedPseRun:
    """从 PSE 用户 YAML 创建 run，并生成只引用 snapshot 的提取请求。"""

    loaded = load_run_config(config_path)
    if not isinstance(loaded, LoadedPseRunConfig):
        raise ManifestStateError(
            f"initialize_pse_run 只接受 PSE，实际为 {loaded.detected_format}"
        )
    if request_writer.backend_name != "pymol-pse":
        raise ManifestStateError(
            f"PSE request writer backend 不匹配: {request_writer.backend_name}"
        )
    timestamp = datetime.now(UTC) if created_at is None else normalize_aware_datetime(created_at)
    selected_run_id = _generated_run_id(timestamp) if run_id is None else run_id

    def prepare(staging: Path, input_snapshot: Path) -> Path:
        request = request_writer.build_request(
            run_root=staging,
            source_path=input_snapshot,
            target_id=loaded.config.target.target_id,
        )
        path = (
            staging
            / str(StageId.TARGET_PREPARATION)
            / "attempt-0001"
            / "inputs"
            / "pse-request.json"
        )
        return request_writer.write_request(request, path)

    workspace, prepared_input = _initialize_workspace(
        loaded=loaded,
        runs_root=runs_root,
        code_commit=code_commit,
        code_identity=code_identity,
        runtime_profile=runtime_profile,
        easydesign_version=easydesign_version,
        selected_run_id=selected_run_id,
        timestamp=timestamp,
        prepare_attempt_input=prepare,
        index_note="Stage 01 PSE import request prepared; worker execution not started.",
    )
    assert prepared_input is not None
    return PreparedPseRun(
        loaded_config=loaded,
        workspace=workspace,
        pse_request=prepared_input,
    )
