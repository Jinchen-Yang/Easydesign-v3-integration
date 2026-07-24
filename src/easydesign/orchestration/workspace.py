"""一次实验一个目录的 Run Workspace 创建和可再生索引。"""

from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from easydesign.backends.structure_prediction import StructurePredictionRequest
from easydesign.backends.target_sources import NormalizedProteinSequence
from easydesign.core import (
    ArtifactRef,
    EvidenceStatus,
    ExecutionStatus,
    ManifestStateError,
    RunManifest,
    StageId,
    dump_model,
    load_model,
)
from easydesign.core.artifacts import ID_PATTERN
from easydesign.core.timestamps import normalize_aware_datetime

from .config import EasyDesignRunConfig, LoadedRunConfig, TargetInputFormat, load_run_config


class PredictionInputWriter(Protocol):
    model_name: str

    def write_input(
        self,
        request: StructurePredictionRequest,
        path: Path,
    ) -> Path: ...


class ResolvedRunConfig(BaseModel):
    """写入 run 的完全解析配置，不包含站点专属后端路径。"""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: str = "0.1"
    project_id: str = Field(pattern=ID_PATTERN)
    run_id: str = Field(pattern=ID_PATTERN)
    user_config: EasyDesignRunConfig
    detected_input_format: TargetInputFormat
    input_snapshot: ArtifactRef
    target: NormalizedProteinSequence
    prediction_request: StructurePredictionRequest
    stop_after_stage: int = Field(ge=1, le=7)


class RunIndexEntry(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    category: str = Field(pattern=ID_PATTERN)
    path: str = Field(min_length=1)
    layout_version: str = Field(min_length=1, max_length=32)
    status: str = Field(min_length=1, max_length=64)
    project_id: str | None = Field(default=None, pattern=ID_PATTERN)
    run_id: str | None = Field(default=None, pattern=ID_PATTERN)
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
        return self


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

    def stage_root(self, stage_id: StageId) -> Path:
        return self.run_root / str(stage_id)

    def attempt_root(self, stage_id: StageId, attempt_id: str) -> Path:
        return self.stage_root(stage_id) / attempt_id


@dataclass(frozen=True, slots=True)
class PreparedSequenceRun:
    loaded_config: LoadedRunConfig
    workspace: RunWorkspace
    protenix_input: Path


def _exclusive_copy(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        with source.open("rb") as input_handle, destination.open("xb") as output_handle:
            shutil.copyfileobj(input_handle, output_handle)
    except FileExistsError as error:
        raise ManifestStateError(f"不可覆盖 run snapshot: {destination}") from error


def _atomic_replace_json(model: BaseModel, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(
        model.model_dump(mode="json", exclude_none=False),
        ensure_ascii=False,
        allow_nan=False,
        indent=2,
        sort_keys=True,
    )
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            handle.write(content)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
            temporary = Path(handle.name)
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


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
        existing = load_model(index_path, RunIndex).entries
    by_path = {entry.path: entry for entry in existing}
    by_path.update({entry.path: entry for entry in entries})
    index = RunIndex(
        generated_at=generated_at,
        entries=tuple(by_path[path] for path in sorted(by_path)),
    )
    _atomic_replace_json(index, index_path)
    return index_path


def _generated_run_id(created_at: datetime) -> str:
    utc = normalize_aware_datetime(created_at)
    return utc.strftime("%Y%m%dt%H%M%Sz").lower()


def _validate_run_id(run_id: str) -> None:
    if re.fullmatch(ID_PATTERN, run_id) is None:
        raise ManifestStateError(f"run_id 不符合稳定 slug 规则: {run_id}")


def initialize_sequence_run(
    *,
    config_path: Path,
    runs_root: Path,
    input_writer: PredictionInputWriter,
    code_commit: str,
    easydesign_version: str,
    run_id: str | None = None,
    created_at: datetime | None = None,
) -> PreparedSequenceRun:
    """从一个用户 YAML 创建完整 run 骨架和 Stage 01 后端输入。"""

    loaded = load_run_config(config_path)
    if input_writer.model_name != loaded.config.structure_prediction.backend:
        raise ManifestStateError(
            "配置 backend 与输入 writer 不一致: "
            f"config={loaded.config.structure_prediction.backend}, "
            f"writer={input_writer.model_name}"
        )
    timestamp = datetime.now(UTC) if created_at is None else normalize_aware_datetime(created_at)
    selected_run_id = _generated_run_id(timestamp) if run_id is None else run_id
    _validate_run_id(selected_run_id)

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
        for stage_id in StageId:
            (staging / str(stage_id)).mkdir()
        (staging / "results").mkdir()

        config_snapshot = staging / "config-snapshot" / "easydesign.yaml"
        input_snapshot = staging / "input-snapshot" / loaded.source_path.name
        _exclusive_copy(loaded.config_path, config_snapshot)
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
        resolved = ResolvedRunConfig(
            project_id=loaded.config.project_id,
            run_id=selected_run_id,
            user_config=loaded.config,
            detected_input_format=loaded.detected_format,
            input_snapshot=input_ref,
            target=loaded.target,
            prediction_request=loaded.prediction_request,
            stop_after_stage=loaded.config.workflow.stop_after_stage,
        )
        resolved_path = staging / "config-snapshot" / "resolved-config.json"
        dump_model(resolved, resolved_path)

        manifest = RunManifest(
            revision=1,
            project_id=loaded.config.project_id,
            run_id=selected_run_id,
            easydesign_version=easydesign_version,
            code_commit=code_commit,
            status=ExecutionStatus.PENDING,
            evidence_status=EvidenceStatus.IMPLEMENTED,
            created_at=timestamp,
            updated_at=timestamp,
            config_snapshot=config_ref,
        )
        manifest_path = staging / "manifests" / "run-manifest.v0001.json"
        dump_model(manifest, manifest_path)

        protenix_input = (
            staging
            / str(StageId.TARGET_PREPARATION)
            / "attempt-0001"
            / "inputs"
            / "protenix-input.json"
        )
        input_writer.write_input(loaded.prediction_request, protenix_input)
        staging.rename(final_root)
    except Exception:
        if staging.exists():
            shutil.rmtree(staging)
        raise

    workspace = RunWorkspace(
        runs_root=root,
        run_root=final_root,
        project_id=loaded.config.project_id,
        run_id=selected_run_id,
        config_snapshot=final_root / "config-snapshot" / "easydesign.yaml",
        input_snapshot=final_root / "input-snapshot" / loaded.source_path.name,
        resolved_config=final_root / "config-snapshot" / "resolved-config.json",
        run_manifest=final_root / "manifests" / "run-manifest.v0001.json",
    )
    final_protenix_input = (
        workspace.attempt_root(StageId.TARGET_PREPARATION, "attempt-0001")
        / "inputs"
        / "protenix-input.json"
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
                notes=("Stage 01 input prepared; backend execution not started.",),
            ),
        ),
        generated_at=timestamp,
    )
    return PreparedSequenceRun(
        loaded_config=loaded,
        workspace=workspace,
        protenix_input=final_protenix_input,
    )
