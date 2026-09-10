"""Immutable, content-addressed execution plans for major research actions."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Annotated, Any, Literal, TypeAlias

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

from easydesign.core import (
    ManifestStateError,
    canonical_model_sha256,
    dump_model,
)
from easydesign.core.artifacts import ID_PATTERN, SHA256_PATTERN
from easydesign.safe_writes import append_pointer_revision, read_last_text_line

from .research_protocols import FirstPilotProtocolSummary, ScaleProtocolSummary


class _PlanBase(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["1.0"] = "1.0"
    project_id: str = Field(pattern=ID_PATTERN)
    created_at: datetime
    foundation_manifest_sha256: str = Field(pattern=SHA256_PATTERN)
    target_mapping_sha256: str = Field(pattern=SHA256_PATTERN)
    backend: str
    resource_summary: dict[str, Any] = Field(default_factory=dict)


class StrategyFreezePlan(_PlanBase):
    plan_type: Literal["strategy-freeze"] = "strategy-freeze"
    strategy_path: str
    strategy_sha256: str = Field(pattern=SHA256_PATTERN)


class PilotExecutionPlan(_PlanBase):
    plan_type: Literal["pilot-execution"] = "pilot-execution"
    strategy_revision: str
    strategy_sha256: str = Field(pattern=SHA256_PATTERN)
    prediction_backend: str
    protocol: FirstPilotProtocolSummary | None = None
    follow_up_candidate_count: int | None = Field(default=None, ge=1)


class PromotionPlan(_PlanBase):
    plan_type: Literal["promotion"] = "promotion"
    pilot_run_id: str
    pilot_manifest_sha256: str = Field(pattern=SHA256_PATTERN)
    strategy_ids: tuple[str, ...] = Field(min_length=1)


class ScaleExecutionPlan(_PlanBase):
    plan_type: Literal["scale-execution"] = "scale-execution"
    selection_id: str
    promotion_receipt_sha256: str = Field(pattern=SHA256_PATTERN)
    source_pilot_manifest_sha256: str = Field(pattern=SHA256_PATTERN)
    protocol: ScaleProtocolSummary


class SelectionPlan(_PlanBase):
    plan_type: Literal["selection"] = "selection"
    production_run_id: str
    production_manifest_sha256: str = Field(pattern=SHA256_PATTERN)
    de_novo_backend: str
    target_conditioned_backend: str
    top_count: int = Field(ge=1)


ExecutionPlan: TypeAlias = Annotated[
    StrategyFreezePlan
    | PilotExecutionPlan
    | PromotionPlan
    | ScaleExecutionPlan
    | SelectionPlan,
    Field(discriminator="plan_type"),
]
_PLAN_ADAPTER: TypeAdapter[ExecutionPlan] = TypeAdapter(ExecutionPlan)


def plan_sha256(plan: ExecutionPlan) -> str:
    return canonical_model_sha256(plan)


def _plan_pointer_name(plan_type: str) -> str:
    return f"{plan_type.upper().replace('-', '_')}_PLAN_CURRENT"


def publish_execution_plan(project_root: Path, plan: ExecutionPlan) -> tuple[Path, str]:
    root = project_root.resolve()
    digest = plan_sha256(plan)
    path = root / "plans" / plan.plan_type / f"plan-{digest}.json"
    if path.exists():
        existing = _PLAN_ADAPTER.validate_json(path.read_text(encoding="utf-8"))
        if canonical_model_sha256(existing) != digest or existing != plan:
            raise ManifestStateError("已存在 execution plan 与 content identity 不一致")
    else:
        dump_model(plan, path)
    append_pointer_revision(
        root / _plan_pointer_name(plan.plan_type),
        path.relative_to(root).as_posix(),
    )
    return path, digest


def load_execution_plan(path: Path) -> ExecutionPlan:
    try:
        plan = _PLAN_ADAPTER.validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise ManifestStateError(f"ExecutionPlan 无法读取: {path}") from error
    expected = path.stem.removeprefix("plan-")
    if expected != plan_sha256(plan):
        raise ManifestStateError("ExecutionPlan filename/content SHA-256 drift")
    return plan


def load_current_execution_plan(project_root: Path, plan_type: str) -> tuple[ExecutionPlan, Path]:
    root = project_root.resolve()
    pointer = root / _plan_pointer_name(plan_type)
    try:
        relative = Path(read_last_text_line(pointer))
    except OSError as error:
        raise ManifestStateError(
            f"缺少 current {plan_type} plan；请先运行 plan/validate"
        ) from error
    if relative.is_absolute() or ".." in relative.parts:
        raise ManifestStateError("ExecutionPlan pointer 非法")
    path = (root / relative).resolve(strict=True)
    if not path.is_relative_to(root):
        raise ManifestStateError("ExecutionPlan pointer 逃出 project")
    return load_execution_plan(path), path


def require_exact_current_plan(
    project_root: Path,
    expected: ExecutionPlan,
    *,
    supplied_sha256: str | None,
) -> tuple[Path, str]:
    current, path = load_current_execution_plan(project_root, expected.plan_type)
    current_sha = plan_sha256(current)
    expected_sha = plan_sha256(expected)
    if supplied_sha256 is not None and supplied_sha256 != current_sha:
        raise ManifestStateError("提供的 plan SHA-256 不是 current immutable plan")
    if current_sha != expected_sha:
        raise ManifestStateError(
            "current inputs/count/backend/mapping 已变化；旧 plan/approval 失效，请重新 plan"
        )
    return path, current_sha


__all__ = [
    "ExecutionPlan",
    "PilotExecutionPlan",
    "PromotionPlan",
    "ScaleExecutionPlan",
    "SelectionPlan",
    "StrategyFreezePlan",
    "load_current_execution_plan",
    "load_execution_plan",
    "plan_sha256",
    "publish_execution_plan",
    "require_exact_current_plan",
]
