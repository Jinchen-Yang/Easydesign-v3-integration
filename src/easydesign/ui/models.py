"""浏览器只读投影和本地 job 的类型化契约。"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class UiStageState(StrEnum):
    DRAFT = "draft"
    VALIDATING = "validating"
    READY = "ready"
    QUEUED = "queued"
    RUNNING = "running"
    AWAITING_HUMAN_APPROVAL = "awaiting-human-approval"
    SUCCEEDED = "succeeded"
    SCIENTIFIC_STOP = "scientific-stop"
    OPERATIONAL_FAILED = "operational-failed"
    NOT_REACHED = "not-reached"
    SIMULATED_PREVIEW = "simulated-preview"


class ArtifactProjection(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    artifact_id: str
    role: str
    file_format: str
    size_bytes: int = Field(ge=0)
    sha256: str
    token: str


class StageCapability(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    status: str
    summary: str


class StageProjection(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    stage_number: int = Field(ge=1, le=7)
    stage_id: str
    title: str
    state: UiStageState
    capability: StageCapability
    summary: str
    evidence_status: str
    selected_attempt_id: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    highlights: dict[str, Any] = Field(default_factory=dict)
    tables: dict[str, list[dict[str, Any]]] = Field(default_factory=dict)
    artifacts: tuple[ArtifactProjection, ...] = ()


class RunProjection(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    run_key: str
    project_id: str
    run_id: str
    status: str
    evidence_status: str
    workflow_state: str | None
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None
    code_version: str
    code_commit: str | None
    profile_id: str | None
    integrity_status: str
    stages: tuple[StageProjection, ...]


class ProjectProjection(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    project_id: str
    run_count: int = Field(ge=0)
    latest_run: RunProjection | None
    runs: tuple[RunProjection, ...]


class ReplayFrame(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    frame_id: str
    label: str
    stage_number: int | None
    state: UiStageState
    description: str


class ReplayTimeline(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    replay_id: str
    source_run_key: str
    source_manifest_sha256: str
    banner: str = "DEMO REPLAY · 不修改科学证据"
    frames: tuple[ReplayFrame, ...]


class UiJobRecord(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: str = "0.1"
    job_id: str
    operation: str
    status: str
    config_path: str | None = None
    run_key: str | None = None
    run_id: str | None = None
    process_id: int | None = None
    drain_requested: bool = False
    created_at: datetime
    updated_at: datetime
    error: str | None = None


class DraftOrderOutcome(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    status: str
    allowed: bool
    reason: str
    candidate_count: int = Field(ge=0)
    package_token: str | None = None
