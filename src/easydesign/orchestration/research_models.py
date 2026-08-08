"""Public, Stage-free result models for the agent-native research product."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

ResearchPhase = Literal["prepare", "strategize", "pilot", "scale", "select"]


class NextAction(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    command: str
    description: str
    approval_required: bool = False


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


__all__ = ["CommandResult", "EvidenceItem", "NextAction", "ResearchPhase"]
