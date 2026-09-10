"""Typed Agent actions with deterministic human CLI rendering."""

from __future__ import annotations

import shlex
from pathlib import Path
from typing import Annotated, Literal, TypeAlias

from pydantic import BaseModel, ConfigDict, Field

from easydesign.core.artifacts import ID_PATTERN, SHA256_PATTERN


class ImmutableInputRef(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str = Field(pattern=ID_PATTERN)
    sha256: str = Field(pattern=SHA256_PATTERN)
    path: str | None = None


class _ActionBase(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    project_id: str = Field(pattern=ID_PATTERN)
    project_path: Path
    immutable_input_refs: tuple[ImmutableInputRef, ...] = ()
    approval_required: bool
    resource_class: Literal["read-only", "metadata-write", "gpu-small", "gpu-large"]


class ReviewStatusIntent(_ActionBase):
    action_type: Literal["review-status"] = "review-status"
    approval_required: Literal[False] = False
    resource_class: Literal["read-only"] = "read-only"
    run_id: str | None = None
    report: str | None = None


class ReviewPilotIntent(_ActionBase):
    action_type: Literal["review-pilot"] = "review-pilot"
    approval_required: Literal[False] = False
    resource_class: Literal["metadata-write"] = "metadata-write"
    run_id: str = Field(pattern=ID_PATTERN)


class InterpretPilotIntent(_ActionBase):
    action_type: Literal["interpret-pilot"] = "interpret-pilot"
    approval_required: Literal[False] = False
    resource_class: Literal["metadata-write"] = "metadata-write"
    run_id: str = Field(pattern=ID_PATTERN)
    input_path: Path


class DraftStrategyIntent(_ActionBase):
    action_type: Literal["draft-strategy"] = "draft-strategy"
    approval_required: Literal[False] = False
    resource_class: Literal["metadata-write"] = "metadata-write"
    source_pilot_run_id: str = Field(pattern=ID_PATTERN)
    research_event_ids: tuple[str, ...] = Field(min_length=3)


class ApproveSiteIntent(_ActionBase):
    action_type: Literal["approve-site"] = "approve-site"
    approval_required: Literal[True] = True
    resource_class: Literal["metadata-write"] = "metadata-write"
    input_path: Path
    plan_sha256: str | None = Field(default=None, pattern=SHA256_PATTERN)


class FreezeStrategyIntent(_ActionBase):
    action_type: Literal["freeze-strategy"] = "freeze-strategy"
    approval_required: Literal[True] = True
    resource_class: Literal["metadata-write"] = "metadata-write"
    strategy_path: Path
    plan_sha256: str = Field(pattern=SHA256_PATTERN)


class RunPilotIntent(_ActionBase):
    action_type: Literal["run-pilot"] = "run-pilot"
    approval_required: Literal[True] = True
    resource_class: Literal["gpu-small"] = "gpu-small"
    strategy_revision: str
    prediction_backend: str
    plan_sha256: str = Field(pattern=SHA256_PATTERN)


class PromotePilotIntent(_ActionBase):
    action_type: Literal["promote-pilot"] = "promote-pilot"
    approval_required: Literal[True] = True
    resource_class: Literal["metadata-write"] = "metadata-write"
    run_id: str
    strategy_ids: tuple[str, ...]
    plan_sha256: str = Field(pattern=SHA256_PATTERN)


class RunScaleIntent(_ActionBase):
    action_type: Literal["run-scale"] = "run-scale"
    approval_required: Literal[True] = True
    resource_class: Literal["gpu-large"] = "gpu-large"
    selection_id: str
    candidate_count: int = Field(ge=1)
    plan_sha256: str = Field(pattern=SHA256_PATTERN)


class RunSelectIntent(_ActionBase):
    action_type: Literal["run-select"] = "run-select"
    approval_required: Literal[True] = True
    resource_class: Literal["gpu-large"] = "gpu-large"
    run_id: str
    de_novo_backend: str
    target_conditioned_backend: str
    top_count: int = Field(ge=1)
    plan_sha256: str = Field(pattern=SHA256_PATTERN)


ActionIntent: TypeAlias = Annotated[
    ReviewStatusIntent
    | ReviewPilotIntent
    | InterpretPilotIntent
    | DraftStrategyIntent
    | ApproveSiteIntent
    | FreezeStrategyIntent
    | RunPilotIntent
    | PromotePilotIntent
    | RunScaleIntent
    | RunSelectIntent,
    Field(discriminator="action_type"),
]


def render_action(intent: ActionIntent) -> str:
    """Render a typed action without asking an Agent to quote shell values."""

    project = str(intent.project_path)
    if isinstance(intent, ReviewStatusIntent):
        command = ["easydesign", "project", "status", project, "--json"]
        if intent.run_id is not None:
            command = ["easydesign", "view", project, "--run", intent.run_id]
            if intent.report is not None:
                command.extend(("--report", intent.report))
    elif isinstance(intent, ReviewPilotIntent):
        command = [
            "easydesign",
            "pilot",
            "review",
            project,
            "--run",
            intent.run_id,
        ]
    elif isinstance(intent, InterpretPilotIntent):
        command = [
            "easydesign",
            "pilot",
            "interpret",
            project,
            "--run",
            intent.run_id,
            "--input",
            str(intent.input_path),
        ]
    elif isinstance(intent, DraftStrategyIntent):
        command = [
            "easydesign",
            "strategy",
            "draft",
            project,
            "--from-pilot",
            intent.source_pilot_run_id,
        ]
    elif isinstance(intent, ApproveSiteIntent):
        command = [
            "easydesign",
            "site",
            "approve",
            project,
            "--input",
            str(intent.input_path),
            "--confirm",
        ]
    elif isinstance(intent, FreezeStrategyIntent):
        command = [
            "easydesign",
            "strategy",
            "freeze",
            project,
            "--config",
            str(intent.strategy_path),
            "--plan-sha",
            intent.plan_sha256,
            "--confirm",
        ]
    elif isinstance(intent, RunPilotIntent):
        command = [
            "easydesign",
            "pilot",
            "run",
            project,
            "--strategy",
            intent.strategy_revision,
            "--prediction-backend",
            intent.prediction_backend,
            "--plan-sha",
            intent.plan_sha256,
            "--confirm",
        ]
    elif isinstance(intent, PromotePilotIntent):
        command = [
            "easydesign",
            "pilot",
            "promote",
            project,
            "--run",
            intent.run_id,
            "--strategy",
            ",".join(intent.strategy_ids),
            "--plan-sha",
            intent.plan_sha256,
            "--confirm",
        ]
    elif isinstance(intent, RunScaleIntent):
        command = [
            "easydesign",
            "scale",
            "run",
            project,
            "--selection",
            intent.selection_id,
            "--count",
            str(intent.candidate_count),
            "--plan-sha",
            intent.plan_sha256,
            "--confirm",
        ]
    else:
        command = [
            "easydesign",
            "select",
            "run",
            project,
            "--run",
            intent.run_id,
            "--top",
            str(intent.top_count),
            "--de-novo-backend",
            intent.de_novo_backend,
            "--target-conditioned-backend",
            intent.target_conditioned_backend,
            "--plan-sha",
            intent.plan_sha256,
            "--confirm",
        ]
    return shlex.join(command)


__all__ = [
    "ActionIntent",
    "ApproveSiteIntent",
    "DraftStrategyIntent",
    "FreezeStrategyIntent",
    "ImmutableInputRef",
    "InterpretPilotIntent",
    "PromotePilotIntent",
    "ReviewPilotIntent",
    "ReviewStatusIntent",
    "RunPilotIntent",
    "RunScaleIntent",
    "RunSelectIntent",
    "render_action",
]
