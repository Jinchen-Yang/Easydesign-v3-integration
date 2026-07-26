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


class MetricPresentation(BaseModel):
    """面向科研用户的指标说明；科学规则仍来自冻结的筛选记录。"""

    model_config = ConfigDict(frozen=True, extra="forbid")

    metric_id: str
    name: str
    abbreviation: str | None = None
    group: str
    definition: str
    unit: str | None = None
    source: str
    direction: str
    role: str
    missing_value_policy: str
    operator: str | None = None
    threshold: float | int | bool | str | None = None


class FilterOverviewProjection(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    run_key: str
    state: UiStageState
    conclusion_title: str
    conclusion: str
    next_actions: tuple[str, ...]
    counts: dict[str, int]
    tier_counts: dict[str, int]
    step_chain: tuple[dict[str, Any], ...]
    failed_rule_counts: dict[str, int]


class StrategyProjection(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    strategy_id: str
    region_id: str
    scaffold_id: str
    candidate_count: int
    unique_sequence_count: int
    hard_pass_count: int
    final_gate_pass_count: int
    final_gate_pass_rate: float
    tier: str
    score_screen: float
    score_yaml: float
    selected_for_expansion: bool


class CandidateListItem(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    candidate_id: str
    phase: str
    strategy_id: str
    sequence_length: int | None = None
    gate_status: str
    score: float | None = None
    metrics: dict[str, float | int | bool | str | None]
    failed_rules: tuple[str, ...] = ()


class CandidatePage(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    phase: str
    page: int = Field(ge=1)
    page_size: int = Field(ge=1, le=100)
    total: int = Field(ge=0)
    total_pages: int = Field(ge=0)
    items: tuple[CandidateListItem, ...]


class CandidateDetailProjection(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    candidate_id: str
    phase: str
    strategy_id: str
    sequence: str | None
    gate_status: str
    score: float | None
    metrics: tuple[dict[str, Any], ...]
    decisions: tuple[dict[str, Any], ...]
    failed_reasons: tuple[str, ...]
    backend_metrics: dict[str, float | int | bool | str | None]
    structures: dict[str, ArtifactProjection]
