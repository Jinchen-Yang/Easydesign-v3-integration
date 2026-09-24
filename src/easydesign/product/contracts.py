"""Versioned browser-facing values; no internal model is an HTTP contract."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ProductError(Exception):
    def __init__(self, code: str, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.code, self.status = code, status


class Value(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ActionRequest(Value):
    request_id: str = Field(pattern=r"^[a-zA-Z0-9_-]{16,96}$")
    revision: str = Field(pattern=r"^[0-9a-f]{64}$")
    action: Literal["approve", "revise", "reject", "override", "resume", "message"]
    card_id: str | None = Field(default=None, max_length=128)
    selected_option_id: str | None = Field(default=None, max_length=256)
    instruction: str | None = Field(default=None, min_length=1, max_length=1500)
    viewed_phase: (
        Literal["goal", "target", "site", "design", "pilot", "scale", "candidates"] | None
    ) = None
    revision_target: str | None = Field(default=None, max_length=64)
    reason: str | None = Field(default=None, max_length=1500)
    acknowledgement: str | None = Field(default=None, max_length=1500)


class CreateProject(Value):
    request_id: str = Field(pattern=r"^[a-zA-Z0-9_-]{16,96}$")
    title: str = Field(min_length=1, max_length=120)
    goal: str = Field(min_length=1, max_length=1500)
    input_id: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")


class RenameProject(Value):
    title: str = Field(min_length=1, max_length=80)


class MetricView(Value):
    id: str
    label: str
    value: bool | int | float | str | None
    unit: str | None = None
    direction: Literal["lower", "higher", "context"] = "context"
    status: Literal["available", "missing"]
    rule_result: Literal["pass", "fail", "unknown"] | None = None
    threshold: float | None = None
    profile_id: str | None = None
    source: str | None = None


class ArtifactView(Value):
    id: str
    label: str
    url: str
    format: str
    size_bytes: int
    sha256: str
    candidate_id: str | None = None
    role: str


class CandidateView(Value):
    id: str
    arm: str
    backend_id: str | None = None
    scaffold: str | None = None
    native_status: Literal["pass", "fail", "incomplete", "not-available"]
    evaluable: bool
    competition_eligible: bool
    independent_prediction: str
    sequence: str | None = None
    sequence_sha256: str
    metrics: list[MetricView]
    artifacts: list[ArtifactView]
    panel_role: Literal["primary", "backup"] | None = None
    failure_reason: str | None = None
    lineage: dict[str, str | int | None] = Field(default_factory=dict)
    structure_roles: dict[str, str] = Field(default_factory=dict)


class Page(Value):
    revision: str
    total: int
    offset: int
    limit: int
    items: list[Any]


class ProjectView(Value):
    id: str
    title: str
    goal: str
    thread_id: str | None
    phase: str
    status: str
    last_activity: int
    validation_only: bool = False
    notice: str | None = None


class WorkbenchProjection(Value):
    schema_version: Literal["1"] = "1"
    mode: Literal["live"] = "live"
    revision: str
    project: ProjectView
    workflow: list[dict[str, Any]]
    current_action: dict[str, Any]
    specialists: list[dict[str, Any]]
    scientific_context: dict[str, Any]
    decision: dict[str, Any] | None
    jobs: list[dict[str, Any]]
    artifacts: list[ArtifactView]
    recent_activity: list[dict[str, Any]]
    tasks: list[dict[str, Any]] = Field(default_factory=list)
    lifecycle: str = "scientific_project"
    event_cursor: int
    candidates: dict[str, Any]
    capabilities: dict[str, bool]
    conversation: list[dict[str, Any]] = Field(default_factory=list)
    requests: list[dict[str, Any]] = Field(default_factory=list)
    connection: Literal["connected"] = "connected"
