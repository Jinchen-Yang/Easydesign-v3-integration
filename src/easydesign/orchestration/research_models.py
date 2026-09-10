"""Public, Stage-free result models for the agent-native research product."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .research_actions import ActionIntent, render_action
from .research_graph import ResearchStateSummary

ResearchPhase = Literal["prepare", "strategize", "pilot", "scale", "select"]


class NextAction(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    command: str
    description: str
    approval_required: bool = False
    intent: ActionIntent | None = None

    @model_validator(mode="after")
    def command_matches_intent(self) -> NextAction:
        if self.intent is not None:
            if self.command != render_action(self.intent):
                raise ValueError("NextAction.command 必须由 typed intent renderer 生成")
            if self.approval_required != self.intent.approval_required:
                raise ValueError("NextAction approval flag 与 typed intent 不一致")
        return self


class EvidenceItem(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: str = Field(min_length=1)
    identity: str = Field(min_length=1)
    status: str
    path: Path | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class CommandResult(BaseModel):
    """Single source for terminal rendering and public JSON output."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["1.0"] = "1.0"
    status: str
    phase: ResearchPhase
    project_id: str
    run_id: str | None = None
    job_id: str | None = None
    manifest: Path | None = None
    artifacts: tuple[Path, ...] = ()
    evidence: tuple[EvidenceItem, ...] = ()
    next_actions: tuple[NextAction, ...] = ()
    warnings: tuple[str, ...] = ()
    research_state: ResearchStateSummary | None = None


__all__ = ["CommandResult", "EvidenceItem", "NextAction", "ResearchPhase"]
