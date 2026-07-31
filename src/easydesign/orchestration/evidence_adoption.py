"""Adopt checksum-verified remote scale evidence without copying its population."""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, TypeVar, cast

from pydantic import BaseModel, ValidationError

from easydesign.backends.executors import SshRemoteExecutor
from easydesign.core import (
    ArtifactRef,
    ConfigurationError,
    ExecutionStatus,
    ManifestStateError,
    ProgressSnapshot,
    RunManifest,
    StageManifest,
    TaskStatus,
    canonical_model_sha256,
    dump_model,
    load_model,
    sha256_file,
)
from easydesign.core.evidence_links import (
    AdoptedDeviceExecutionSummary,
    AdoptedScaleExecutionSummary,
    PolicyReevaluationRecord,
    ProjectScaleEvidenceContinuation,
    ReevaluatedStrategy,
    RunEvidenceLink,
    ScaleEvidenceAdoptionRecord,
)
from easydesign.safe_writes import append_pointer_revision, read_last_text_line
from easydesign.stages.s05_pilot_filtering import PilotFilterReport, Stage05Bundle
from easydesign.stages.s06_scale_generation_and_refolding import (
    ScaleBundle,
    ScaleCoverageReport,
    ScalePlan,
    ScaleTaskTable,
)
from easydesign.workspace_context import WorkspaceContext

from .remote_execution import resolve_remote_executor

ModelT = TypeVar("ModelT", bound=BaseModel)
_STAGE05_ID = "05-pilot-filtering"
_STAGE06_ID = "06-scale-generation-and-refolding"
_StrategyTier = Literal["tier-a", "tier-b", "tier-c", "tier-d"]


def _strategy_tier(value: object) -> _StrategyTier:
    normalized = str(value)
    if normalized not in {"tier-a", "tier-b", "tier-c", "tier-d"}:
        raise ManifestStateError(f"未知 Stage 05 strategy tier: {normalized}")
    return cast(_StrategyTier, normalized)


def _latest_local_manifest(run_root: Path) -> tuple[RunManifest, Path]:
    pointer = run_root / "manifests" / "LATEST"
    if not pointer.is_file():
        raise ManifestStateError(f"local evidence run 缺少 LATEST: {pointer}")
    name = read_last_text_line(pointer)
    if Path(name).name != name:
        raise ManifestStateError("local evidence LATEST 不是安全文件名")
    path = run_root / "manifests" / name
    manifest = load_model(path, RunManifest)
    return manifest, path


def _stage_manifest(
    run_root: Path,
    run: RunManifest,
    stage_id: str,
) -> tuple[StageManifest, ArtifactRef]:
    reference = next(
        (item for item in run.stage_manifest_refs if item.producer_stage == stage_id),
        None,
    )
    if reference is None:
        raise ManifestStateError(f"run 未声明 {stage_id} manifest")
    return load_model(reference.verify(run_root), StageManifest), reference


def _evidence_link(
    *,
    project_id: str,
    run_id: str,
    run_manifest_sha256: str,
    artifact: ArtifactRef,
    executor_id: str,
) -> RunEvidenceLink:
    return RunEvidenceLink(
        source_project_id=project_id,
        source_run_id=run_id,
        source_run_manifest_sha256=run_manifest_sha256,
        source_artifact=artifact,
        executor_id=executor_id,
        artifact_sha256=artifact.sha256,
        artifact_size_bytes=artifact.size_bytes,
    )


def reevaluate_frozen_stage05(
    local_run_root: Path,
    *,
    executor_id: str = "proteindigger-local",
    generated_at: datetime | None = None,
) -> tuple[PolicyReevaluationRecord, RunManifest, str]:
    """Apply v1.6 promotion semantics to an unchanged v1.5 pilot report."""

    root = local_run_root.expanduser().resolve()
    run, run_path = _latest_local_manifest(root)
    stage, _ = _stage_manifest(root, run, _STAGE05_ID)
    if stage.status is not ExecutionStatus.SUCCEEDED:
        raise ManifestStateError("policy reevaluation 只接受 succeeded Stage 05")
    bundle_ref = stage.require_output("stage05-bundle")
    report_ref = stage.require_output("pilot-filter-report")
    bundle = load_model(bundle_ref.verify(root), Stage05Bundle)
    report = load_model(report_ref.verify(root), PilotFilterReport)
    if bundle.pilot_filter_report.sha256 != report_ref.sha256:
        raise ManifestStateError("Stage05Bundle pilot report identity 不一致")
    if bundle.status != "stopped-no-scale-winner":
        raise ManifestStateError(
            "当前 adoption 只接受冻结的 v1.5 stopped-no-scale-winner 证据"
        )
    tier_a = sorted(
        (item for item in report.strategy_summaries if str(item.tier) == "tier-a"),
        key=lambda item: (-item.score_yaml, item.strategy_id),
    )[:3]
    promoted_ranks = {
        item.strategy_id: rank for rank, item in enumerate(tier_a, start=1)
    }
    strategies = tuple(
        ReevaluatedStrategy(
            strategy_id=item.strategy_id,
            tier=_strategy_tier(item.tier),
            score_yaml=item.score_yaml,
            old_selected_for_expansion=item.selected_for_expansion,
            new_promoted=item.strategy_id in promoted_ranks,
            promotion_rank=promoted_ranks.get(item.strategy_id),
        )
        for item in report.strategy_summaries
    )
    promoted = tuple(item.strategy_id for item in tier_a)
    run_sha256 = sha256_file(run_path)
    return (
        PolicyReevaluationRecord(
            generated_at=generated_at or datetime.now(tz=UTC),
            source_stage05_bundle=_evidence_link(
                project_id=run.project_id,
                run_id=run.run_id,
                run_manifest_sha256=run_sha256,
                artifact=bundle_ref,
                executor_id=executor_id,
            ),
            source_stage05_status=bundle.status,
            strategies=strategies,
            promoted_strategy_ids=promoted,
            status="strategies-promoted" if promoted else "stopped-no-tier-a",
        ),
        run,
        run_sha256,
    )


def _remote_text(executor: SshRemoteExecutor, remote_path: Path) -> str:
    if not executor.is_file(remote_path):
        raise ManifestStateError(f"remote evidence 文件不存在: {remote_path.name}")
    return executor.read_text(remote_path)


def _remote_model(
    executor: SshRemoteExecutor,
    remote_path: Path,
    model_type: type[ModelT],
    *,
    expected: ArtifactRef | None = None,
) -> ModelT:
    identity = executor.file_identity(remote_path)
    if expected is not None and (
        identity.sha256 != expected.sha256
        or identity.size_bytes != expected.size_bytes
    ):
        raise ManifestStateError(
            f"remote evidence identity 与 ArtifactRef 不一致: {expected.artifact_id}"
        )
    try:
        return model_type.model_validate_json(_remote_text(executor, remote_path))
    except ValidationError as error:
        raise ManifestStateError(
            f"remote evidence schema 无效: {remote_path.name}: {error}"
        ) from error


def _remote_artifact_model(
    executor: SshRemoteExecutor,
    remote_run_root: Path,
    reference: ArtifactRef,
    model_type: type[ModelT],
) -> ModelT:
    return _remote_model(
        executor,
        remote_run_root / reference.relative_path,
        model_type,
        expected=reference,
    )


def _remote_link(
    *,
    run: RunManifest,
    run_sha256: str,
    artifact: ArtifactRef,
    executor_id: str,
) -> RunEvidenceLink:
    return _evidence_link(
        project_id=run.project_id,
        run_id=run.run_id,
        run_manifest_sha256=run_sha256,
        artifact=artifact,
        executor_id=executor_id,
    )


def _device_summaries(task_table: ScaleTaskTable) -> tuple[AdoptedDeviceExecutionSummary, ...]:
    task_count: dict[int, int] = defaultdict(int)
    attempt_count: dict[int, int] = defaultdict(int)
    failed_attempt_count: dict[int, int] = defaultdict(int)
    candidate_count: dict[int, int] = defaultdict(int)
    busy_seconds: dict[int, float] = defaultdict(float)
    for task in task_table.tasks:
        if task.status is not TaskStatus.SUCCEEDED or not task.attempts:
            raise ManifestStateError("adopted Stage 06 task 必须全部 succeeded")
        final_device = task.attempts[-1].device
        task_count[final_device] += 1
        candidate_count[final_device] += task.collected_candidates
        for attempt in task.attempts:
            attempt_count[attempt.device] += 1
            failed_attempt_count[attempt.device] += int(
                attempt.status is TaskStatus.FAILED
            )
            if attempt.ended_at is not None:
                busy_seconds[attempt.device] += max(
                    0.0,
                    (attempt.ended_at - attempt.started_at).total_seconds(),
                )
    return tuple(
        AdoptedDeviceExecutionSummary(
            device=device,
            task_count=task_count[device],
            attempt_count=attempt_count[device],
            failed_attempt_count=failed_attempt_count[device],
            candidate_count=candidate_count[device],
            busy_seconds=busy_seconds[device],
        )
        for device in sorted(task_count)
    )


def adopt_remote_scale_evidence(
    *,
    local_run_root: Path,
    remote_run_root: Path,
    executor_id: str,
    continuation_id: str,
    profile_path: Path | None = None,
    generated_at: datetime | None = None,
) -> ProjectScaleEvidenceContinuation:
    """Publish a small immutable record linking frozen Stage 05 to remote Stage 06."""

    now = generated_at or datetime.now(tz=UTC)
    local_root = local_run_root.expanduser().resolve()
    context = WorkspaceContext.discover(local_root)
    policy, local_run, local_manifest_sha256 = reevaluate_frozen_stage05(
        local_root,
        generated_at=now,
    )
    if policy.status != "strategies-promoted":
        raise ManifestStateError("没有 Tier A 时不能采用 Stage 06 population")
    executor = resolve_remote_executor(
        profile_path=profile_path,
        executor_id=executor_id,
    )
    remote_root = remote_run_root
    if not remote_root.is_absolute():
        raise ConfigurationError("remote run root 必须是显式绝对路径")
    latest_name = _remote_text(executor, remote_root / "manifests" / "LATEST").strip()
    if Path(latest_name).name != latest_name:
        raise ManifestStateError("remote LATEST 不是安全文件名")
    remote_manifest_path = remote_root / "manifests" / latest_name
    remote_identity = executor.file_identity(remote_manifest_path)
    remote_run = _remote_model(executor, remote_manifest_path, RunManifest)
    if remote_run.status is not ExecutionStatus.SUCCEEDED:
        raise ManifestStateError("remote Stage 06 source run 必须是 succeeded")
    if remote_run.project_id != local_run.project_id:
        raise ManifestStateError("local Stage 05 与 remote Stage 06 project 不一致")
    remote_stage, stage_ref = next(
        (
            (
                _remote_artifact_model(
                    executor,
                    remote_root,
                    reference,
                    StageManifest,
                ),
                reference,
            )
            for reference in remote_run.stage_manifest_refs
            if reference.producer_stage == _STAGE06_ID
        ),
        (None, None),
    )
    if remote_stage is None or stage_ref is None:
        raise ManifestStateError("remote run 未声明 Stage 06 manifest")
    if remote_stage.status is not ExecutionStatus.SUCCEEDED:
        raise ManifestStateError("remote Stage 06 manifest 不是 succeeded")
    scale_bundle_ref = remote_stage.require_output("scale-bundle")
    scale_plan_ref = remote_stage.require_output("scale-plan")
    scale_progress_ref = remote_stage.require_output("scale-progress-final")
    candidate_index_ref = remote_stage.require_output("scale-candidate-index")
    coverage_ref = remote_stage.require_output("scale-coverage-report")
    task_table_ref = remote_stage.require_output("scale-task-table")
    scale_bundle = _remote_artifact_model(
        executor, remote_root, scale_bundle_ref, ScaleBundle
    )
    scale_plan = _remote_artifact_model(executor, remote_root, scale_plan_ref, ScalePlan)
    progress = _remote_artifact_model(
        executor, remote_root, scale_progress_ref, ProgressSnapshot
    )
    coverage = _remote_artifact_model(
        executor, remote_root, coverage_ref, ScaleCoverageReport
    )
    task_table = _remote_artifact_model(
        executor, remote_root, task_table_ref, ScaleTaskTable
    )
    candidate_identity = executor.file_identity(
        remote_root / candidate_index_ref.relative_path
    )
    if (
        candidate_identity.sha256 != candidate_index_ref.sha256
        or candidate_identity.size_bytes != candidate_index_ref.size_bytes
    ):
        raise ManifestStateError("remote candidate index identity 不一致")
    promoted = policy.promoted_strategy_ids
    if promoted != (scale_bundle.strategy_id,):
        raise ManifestStateError(
            "remote historical scale strategy 与 v1.6 promotion 不一致"
        )
    if scale_bundle.stage05_bundle.sha256 != (
        policy.source_stage05_bundle.artifact_sha256
    ):
        raise ManifestStateError("remote ScaleBundle 引用的 Stage 05 identity 不一致")
    expected = scale_bundle.requested_new_candidates
    if (
        scale_bundle.complete_new_candidates != expected
        or scale_plan.requested_new_candidates != expected
        or coverage.complete_new_candidates != expected
        or progress.planned_candidates != expected
        or progress.collected_candidates != expected
        or progress.succeeded_tasks != scale_bundle.shard_count
        or progress.failed_tasks
        or progress.status != "succeeded"
        or len(task_table.tasks) != scale_bundle.shard_count
    ):
        raise ManifestStateError("remote Stage 06 数量、任务或进度证据不一致")
    device_execution = _device_summaries(task_table)
    strategy_shard_counts: dict[str, int] = defaultdict(int)
    strategy_candidate_counts: dict[str, int] = defaultdict(int)
    for task in task_table.tasks:
        strategy_shard_counts[task.strategy_id] += 1
        strategy_candidate_counts[task.strategy_id] += task.collected_candidates
    if set(strategy_shard_counts) != set(promoted):
        raise ManifestStateError("remote task table strategy 与 v1.6 promotion 不一致")
    execution = AdoptedScaleExecutionSummary(
        executor_id=executor_id,
        strategy_ids=promoted,
        strategy_candidate_counts=dict(strategy_candidate_counts),
        strategy_shard_counts=dict(strategy_shard_counts),
        devices=tuple(item.device for item in device_execution),
        shard_count=scale_bundle.shard_count,
        succeeded_task_count=progress.succeeded_tasks,
        failed_task_count=progress.failed_tasks,
        candidate_count=progress.collected_candidates,
        elapsed_seconds=progress.elapsed_seconds,
        completed_at=progress.updated_at,
    )
    scale_link = _remote_link(
        run=remote_run,
        run_sha256=remote_identity.sha256,
        artifact=scale_bundle_ref,
        executor_id=executor_id,
    )
    adoption = ScaleEvidenceAdoptionRecord(
        generated_at=now,
        policy_reevaluation_sha256=canonical_model_sha256(policy),
        source_scale_bundle=scale_link,
        strategy_ids=promoted,
        shard_count=scale_bundle.shard_count,
        candidate_count=expected,
        expected_candidate_count=expected,
    )
    continuation = ProjectScaleEvidenceContinuation(
        continuation_id=continuation_id,
        generated_at=now,
        project_id=local_run.project_id,
        source_local_run_id=local_run.run_id,
        source_local_run_manifest_sha256=local_manifest_sha256,
        policy_reevaluation=policy,
        scale_evidence_adoption=adoption,
        source_stage06_manifest=_remote_link(
            run=remote_run,
            run_sha256=remote_identity.sha256,
            artifact=stage_ref,
            executor_id=executor_id,
        ),
        source_scale_plan=_remote_link(
            run=remote_run,
            run_sha256=remote_identity.sha256,
            artifact=scale_plan_ref,
            executor_id=executor_id,
        ),
        source_scale_progress=_remote_link(
            run=remote_run,
            run_sha256=remote_identity.sha256,
            artifact=scale_progress_ref,
            executor_id=executor_id,
        ),
        source_candidate_index=_remote_link(
            run=remote_run,
            run_sha256=remote_identity.sha256,
            artifact=candidate_index_ref,
            executor_id=executor_id,
        ),
        execution=execution,
        device_execution=device_execution,
    )
    destination_root = context.projects_root / local_run.project_id / "evidence-adoptions"
    context.assert_write_path(destination_root)
    record_path = destination_root / continuation_id / "record.json"
    dump_model(continuation, record_path)
    append_pointer_revision(destination_root / "CURRENT", f"{continuation_id}/record.json")
    return continuation


def load_project_scale_evidence(
    projects_root: Path,
    project_id: str,
) -> ProjectScaleEvidenceContinuation | None:
    """Load the latest immutable project evidence record, if explicitly published."""

    root = projects_root.resolve() / project_id / "evidence-adoptions"
    pointer = root / "CURRENT"
    if not pointer.is_file():
        return None
    relative = read_last_text_line(pointer)
    candidate = (root / relative).resolve()
    if not candidate.is_relative_to(root) or not candidate.is_file():
        raise ManifestStateError("project scale evidence pointer 无效")
    return load_model(candidate, ProjectScaleEvidenceContinuation)


def load_verified_project_scale_evidence(
    run_root: Path,
    projects_root: Path,
) -> ProjectScaleEvidenceContinuation | None:
    """Return the current adoption only when its frozen local source still matches."""

    root = run_root.resolve()
    run, run_manifest_path = _latest_local_manifest(root)
    continuation = load_project_scale_evidence(projects_root, run.project_id)
    if continuation is None or continuation.source_local_run_id != run.run_id:
        return None
    if continuation.source_local_run_manifest_sha256 != sha256_file(
        run_manifest_path
    ):
        raise ManifestStateError("project scale evidence 的 local run identity 已失效")
    continuation.policy_reevaluation.source_stage05_bundle.source_artifact.verify(root)
    return continuation


__all__ = [
    "adopt_remote_scale_evidence",
    "load_project_scale_evidence",
    "load_verified_project_scale_evidence",
    "reevaluate_frozen_stage05",
]
