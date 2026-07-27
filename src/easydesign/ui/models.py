"""浏览器只读投影和本地 job 的类型化契约。"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

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


class TaskExecutionProjection(BaseModel):
    """一个执行任务的产品投影；科学候选质量不在这里判断。"""

    model_config = ConfigDict(frozen=True, extra="forbid")

    task_id: str
    strategy_id: str
    status: str
    requested_candidates: int = Field(ge=0)
    collected_candidates: int = Field(ge=0)
    attempt_count: int = Field(ge=0)
    retry_count: int = Field(ge=0)
    last_device: int | None = Field(default=None, ge=0)
    latest_heartbeat_at: datetime | None = None
    heartbeat_elapsed_seconds: float | None = Field(default=None, ge=0)
    heartbeat_message: str | None = None


class DeviceExecutionProjection(BaseModel):
    """单个计算设备的当前任务和历史工作量。"""

    model_config = ConfigDict(frozen=True, extra="forbid")

    device: int = Field(ge=0)
    current_task_id: str | None = None
    current_strategy_id: str | None = None
    assigned_task_count: int = Field(ge=0)
    succeeded_task_count: int = Field(ge=0)
    attempt_count: int = Field(ge=0)
    failed_attempt_count: int = Field(ge=0)
    collected_candidates: int = Field(ge=0)
    busy_seconds: float = Field(ge=0)
    latest_heartbeat_at: datetime | None = None
    heartbeat_elapsed_seconds: float | None = Field(default=None, ge=0)
    heartbeat_message: str | None = None
    tasks: tuple[TaskExecutionProjection, ...] = ()


class ExecutionProgressProjection(BaseModel):
    """Stage 04/06 共用的实时与历史执行投影。"""

    model_config = ConfigDict(frozen=True, extra="forbid")

    stage_number: int = Field(ge=1, le=7)
    stage_id: str
    status: str
    updated_at: datetime
    total_tasks: int = Field(ge=0)
    pending_tasks: int = Field(ge=0)
    waiting_tasks: int = Field(ge=0)
    running_tasks: int = Field(ge=0)
    succeeded_tasks: int = Field(ge=0)
    failed_tasks: int = Field(ge=0)
    planned_candidates: int = Field(ge=0)
    collected_candidates: int = Field(ge=0)
    elapsed_seconds: float = Field(ge=0)
    throughput_candidates_per_hour: float | None = Field(default=None, ge=0)
    estimated_remaining_seconds: float | None = Field(default=None, ge=0)
    device_history_status: str
    devices: tuple[DeviceExecutionProjection, ...] = ()
    recent_events: tuple[dict[str, Any], ...] = ()
    recent_errors: tuple[str, ...] = ()


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
    session_id: str | None = None
    stage_number: int | None = Field(default=None, ge=1, le=7)
    process_id: int | None = None
    drain_requested: bool = False
    created_at: datetime
    updated_at: datetime
    error: str | None = None


class DesignConfigRevision(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    revision: int = Field(ge=1)
    stage_number: int = Field(ge=1, le=7)
    relative_path: str
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    created_at: datetime


class DesignSession(BaseModel):
    """产品流程记录；不替代或修改科学 RunManifest。"""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["0.1"] = "0.1"
    session_id: str
    project_id: str
    design_mode: Literal["full-workflow", "stepwise", "developer-smoke"]
    execution_mode: Literal["unattended", "review-gated"]
    current_stage: int = Field(default=1, ge=1, le=7)
    status: Literal[
        "draft",
        "ready",
        "running",
        "awaiting-human-approval",
        "succeeded",
        "scientific-stop",
        "operational-failed",
    ] = "draft"
    config_revisions: tuple[DesignConfigRevision, ...] = ()
    run_lineage: tuple[str, ...] = ()
    created_at: datetime
    updated_at: datetime


class SelfTestRecord(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["0.1"] = "0.1"
    self_test_id: str
    mode: Literal["deterministic-seven-stage", "real-backend-micro"]
    status: str
    engineering_status: str
    backend_status: str
    scientific_status: str
    stage_statuses: dict[str, str] = Field(default_factory=dict)
    run_key: str | None = None
    environment: dict[str, str] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime
    message: str


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


class StrategyMetricAggregate(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    metric_id: str
    observed_count: int = Field(ge=0)
    missing_count: int = Field(ge=0)
    mean: float | None = None
    median: float | None = None
    minimum: float | None = None
    maximum: float | None = None


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
    score_screen_top_quartile_mean: float
    score_yaml: float
    selected_for_expansion: bool
    configuration: dict[str, Any] = Field(default_factory=dict)
    metric_aggregates: tuple[StrategyMetricAggregate, ...] = ()
    yaml_artifact: ArtifactProjection | None = None


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


class RegionEditorResidue(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    label_seq_id: int = Field(ge=1)
    amino_acid: str = Field(min_length=1, max_length=3)
    sequence_index: int = Field(ge=1)
    auth_chain_id: str
    auth_residue_id: str
    insertion_code: str | None = None
    reference_position: int | None = Field(default=None, ge=1)
    source_color: str | None = None
    current_region: str | None = Field(default=None, pattern=r"^[ABC]$")


class RegionEditorProjection(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    run_key: str
    target_id: str
    target_structure_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    structure: ArtifactProjection
    source_annotation_status: str
    current_region_source: str | None = None
    residues: tuple[RegionEditorResidue, ...]
