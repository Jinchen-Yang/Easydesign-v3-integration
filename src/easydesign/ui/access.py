"""Run-lineage stage access derived only from immutable manifests."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from easydesign.core import ConfigurationError, ExecutionStatus, ManifestStateError
from easydesign.core.manifests import RunManifest, StageManifest
from easydesign.core.serialization import load_model
from easydesign.safe_writes import read_last_text_line

from .models import StageAccessProjection, UiStageState


@dataclass(frozen=True, slots=True)
class StageLockedError(ConfigurationError):
    stage_number: int
    locked_by_stage: int
    locked_at: datetime | None
    reason: str

    def __str__(self) -> str:
        return self.reason

    def detail(self) -> dict[str, object]:
        return {
            "code": "stage_locked",
            "stage_number": self.stage_number,
            "locked_by_stage": self.locked_by_stage,
            "locked_at": (
                None if self.locked_at is None else self.locked_at.isoformat()
            ),
            "reason": self.reason,
        }


def load_run_and_stages(
    run_root: Path,
) -> tuple[RunManifest, dict[int, StageManifest]]:
    pointer = run_root / "manifests" / "LATEST"
    try:
        manifest_path = run_root / "manifests" / read_last_text_line(pointer)
        run_manifest = load_model(manifest_path, RunManifest)
    except (OSError, ValueError) as error:
        raise ManifestStateError(f"无法读取当前 RunManifest: {run_root}") from error
    stages: dict[int, StageManifest] = {}
    for reference in run_manifest.stage_manifest_refs:
        number = int(str(reference.producer_stage).split("-", maxsplit=1)[0])
        stages[number] = load_model(reference.verify(run_root), StageManifest)
    return run_manifest, stages


def highest_accepted_stage(
    run_root: Path,
    *,
    accepted_job_stage: int | None = None,
    accepted_job_at: datetime | None = None,
) -> tuple[int, datetime | None]:
    _, stages = load_run_and_stages(run_root)
    manifest_highest = max(stages, default=0)
    highest = max(manifest_highest, accepted_job_stage or 0)
    locked_at = (
        stages[highest].created_at
        if highest in stages
        else accepted_job_at
    )
    return highest, locked_at


def assert_stage_configurable(
    run_root: Path,
    stage_number: int,
    *,
    accepted_job_stage: int | None = None,
    accepted_job_at: datetime | None = None,
) -> None:
    """Reject edits to an accepted stage and non-sequential continuation."""

    _, stages = load_run_and_stages(run_root)
    manifest_highest = max(stages, default=0)
    highest = max(manifest_highest, accepted_job_stage or 0)
    if stage_number <= highest:
        locked_at = (
            stages[highest].created_at
            if highest in stages
            else accepted_job_at
        )
        raise StageLockedError(
            stage_number=stage_number,
            locked_by_stage=highest,
            locked_at=locked_at,
            reason=(
                f"本运行已受理第{highest}步；第1–{highest}步结果已经冻结。"
                "如需改变上游输入或科学配置，请从“新建设计”创建独立项目。"
            ),
        )
    if stage_number != highest + 1:
        raise ConfigurationError(
            f"只能配置唯一下一阶段：当前应为第{highest + 1}步"
        )
    incomplete = [
        number
        for number in range(1, highest + 1)
        if number not in stages
        or stages[number].status is not ExecutionStatus.SUCCEEDED
    ]
    if incomplete:
        raise ConfigurationError(
            "上游阶段尚未连续成功，不能配置下一阶段: "
            + ", ".join(str(value) for value in incomplete)
        )


def assert_not_locked_by_downstream(
    run_root: Path,
    stage_number: int,
    *,
    accepted_job_stage: int | None = None,
    accepted_job_at: datetime | None = None,
) -> None:
    """Allow an in-stage approval, but reject it after downstream acceptance."""

    _, stages = load_run_and_stages(run_root)
    highest = max(max(stages, default=0), accepted_job_stage or 0)
    if highest > stage_number:
        locked_at = (
            stages[highest].created_at
            if highest in stages
            else accepted_job_at
        )
        raise StageLockedError(
            stage_number=stage_number,
            locked_by_stage=highest,
            locked_at=locked_at,
            reason=(
                f"本运行已经进入第{highest}步；第{stage_number}步审批记录只读，"
                "不能重新批准或回写。"
            ),
        )


def project_stage_access(
    *,
    stage_number: int,
    state: UiStageState,
    stages: dict[int, StageManifest],
    accepted_job_stage: int | None = None,
    accepted_job_at: datetime | None = None,
) -> StageAccessProjection:
    highest = max(max(stages, default=0), accepted_job_stage or 0)
    locked_at = (
        stages[highest].created_at
        if highest in stages
        else accepted_job_at
    )
    if stage_number <= highest:
        access = (
            "running"
            if (
                state in {UiStageState.QUEUED, UiStageState.RUNNING}
                or (
                    accepted_job_stage == stage_number
                    and stage_number not in stages
                )
            )
            else "view-only"
        )
        return StageAccessProjection(
            stage_number=stage_number,
            access=access,
            locked_by_stage=highest,
            locked_at=locked_at,
            reason=(
                f"本运行已进入第{highest}步，上游结果已冻结。"
                if access == "view-only"
                else f"第{stage_number}步已受理并正在执行，配置已经冻结。"
            ),
            allowed_actions=(
                "view",
                "download",
                "display-only-assistant",
                "resume-same-attempt",
            ),
        )
    contiguous_success = all(
        number in stages and stages[number].status is ExecutionStatus.SUCCEEDED
        for number in range(1, stage_number)
    )
    if stage_number == highest + 1 and contiguous_success:
        return StageAccessProjection(
            stage_number=stage_number,
            access="configure",
            locked_by_stage=highest or None,
            locked_at=locked_at,
            reason="上游结果已冻结且连续成功，可以配置唯一下一阶段。",
            allowed_actions=("view-upstream", "configure", "start"),
        )
    return StageAccessProjection(
        stage_number=stage_number,
        access="not-reached",
        locked_by_stage=highest or None,
        locked_at=locked_at,
        reason="请先完成唯一的上一阶段。",
        allowed_actions=("view-description",),
    )
