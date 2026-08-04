"""把不可变 manifest/artifact 投影成浏览器安全的阶段视图。"""

from __future__ import annotations

import json
import statistics
from collections.abc import Iterator, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]

from easydesign.core import (
    ArtifactRef,
    ExecutionStatus,
    ManifestStateError,
    RunManifest,
    StageManifest,
    canonical_model_sha256,
    load_model,
)
from easydesign.core.hashing import sha256_file
from easydesign.orchestration import RunIndex, list_runs
from easydesign.orchestration.evidence_adoption import (
    load_verified_project_scale_evidence,
)
from easydesign.orchestration.task_tracking import load_latest_runtime_model
from easydesign.safe_writes import read_last_text_line

from .access import project_stage_access
from .models import (
    ArtifactProjection,
    DraftOrderOutcome,
    ProjectDraftProjection,
    ProjectMetadata,
    ProjectProjection,
    ReplayFrame,
    ReplayTimeline,
    RunProjection,
    StageAccessProjection,
    StageCapability,
    StageProjection,
    UiStageState,
)
from .security import ArtifactTokenSigner, UiRunRegistry

STAGE_IDS = (
    "01-target-preparation",
    "02-hotspot-discovery",
    "03-boltzgen-configuration",
    "04-pilot-generation",
    "05-pilot-filtering",
    "06-scale-generation-and-refolding",
    "07-final-filtering-and-selection",
)
STAGE_TITLES = (
    "Target 准备",
    "区域发现与批准",
    "BoltzGen 策略",
    "Pilot 生成",
    "Pilot 筛选",
    "规模生成",
    "最终筛选与选择",
)
STAGE_CAPABILITIES = (
    StageCapability(status="smoke-validated", summary="六入口 Target Bundle 与 Viewer"),
    StageCapability(status="planned", summary="自动与用户区域交接已实现，科学验证待完成"),
    StageCapability(status="smoke-validated", summary="基础 VHH strategy compiler"),
    StageCapability(status="smoke-validated", summary="可恢复多 GPU pilot executor"),
    StageCapability(status="smoke-validated", summary="v1.5 filter 与科学停止"),
    StageCapability(status="implemented", summary="2×500 / 20×2500 分片能力"),
    StageCapability(status="implemented", summary="三 seed、TNP 与主备候选包"),
)


def _latest_run_manifest(run_root: Path) -> tuple[RunManifest, Path]:
    pointer = run_root / "manifests" / "LATEST"
    try:
        name = read_last_text_line(pointer)
    except OSError as error:
        raise ManifestStateError(f"无法读取 RunManifest LATEST: {pointer}") from error
    path = run_root / "manifests" / name
    return load_model(path, RunManifest), path


def _load_structured_artifact(run_root: Path, artifact: ArtifactRef) -> Any:
    path = artifact.verify(run_root)
    if path.stat().st_size > 32 * 1024 * 1024:
        raise ManifestStateError(f"UI 摘要 artifact 超过 32 MiB: {artifact.artifact_id}")
    text = path.read_text(encoding="utf-8")
    if artifact.file_format == "json":
        return json.loads(text)
    if artifact.file_format in {"yaml", "yml"}:
        return yaml.safe_load(text)
    raise ManifestStateError(f"UI 摘要不支持格式: {artifact.file_format}")


def _artifacts_by_id(manifest: StageManifest) -> dict[str, ArtifactRef]:
    return {item.artifact_id: item for item in manifest.output_artifacts}


def _optional_data(
    run_root: Path,
    artifacts: dict[str, ArtifactRef],
    artifact_id: str,
) -> Any | None:
    artifact = artifacts.get(artifact_id)
    return None if artifact is None else _load_structured_artifact(run_root, artifact)


def _number_range(values: list[float]) -> list[float] | None:
    return None if not values else [min(values), max(values)]


def _stage_highlights(
    stage_number: int,
    run_root: Path,
    manifest: StageManifest,
) -> tuple[dict[str, Any], dict[str, list[dict[str, Any]]]]:
    artifacts = _artifacts_by_id(manifest)
    highlights: dict[str, Any] = {}
    tables: dict[str, list[dict[str, Any]]] = {}
    if stage_number == 1:
        bundle = _optional_data(run_root, artifacts, "target-bundle") or {}
        quality = _optional_data(run_root, artifacts, "structure-quality") or {}
        ensemble = bundle.get("coordinate_ensemble") or {}
        highlights = {
            "target_id": bundle.get("target_id"),
            "origin": bundle.get("origin"),
            "sequence_length": bundle.get("sequence_length"),
            "model_count": ensemble.get("model_count", 1),
            "missing_ca_count": quality.get("missing_ca_count"),
            "protein_chain_count": quality.get("protein_chain_count"),
        }
    elif stage_number == 2:
        hotspots = _optional_data(run_root, artifacts, "hotspots") or {}
        regions = hotspots.get("hotspot_sets") or []
        highlights = {
            "region_count": len(regions),
            "region_source": (hotspots.get("region_source") or {}).get("type"),
            "approved_by": hotspots.get("approved_by"),
            "approval_authority": hotspots.get("approval_authority"),
            "approval_source": hotspots.get("approval_source"),
            "selection_basis": hotspots.get("selection_basis"),
            "ready_for_stage03": hotspots.get("ready_for_stage03"),
        }
        tables["regions"] = [
            {
                "id": region.get("id"),
                "design_goal": region.get("design_goal"),
                "member_count": len(region.get("label_seq_ids") or []),
                "label_ranges": region.get("label_ranges"),
                "risk_flags": region.get("risk_flags") or [],
            }
            for region in regions
        ]
    elif stage_number == 3:
        matrix = _optional_data(run_root, artifacts, "design-matrix") or {}
        strategies = matrix.get("strategies") or []
        regions = sorted({item.get("region_id") for item in strategies if item.get("region_id")})
        scaffolds = sorted(
            {item.get("scaffold_id") for item in strategies if item.get("scaffold_id")}
        )
        highlights = {
            "strategy_count": len(strategies),
            "region_count": len(regions),
            "scaffold_count": len(scaffolds),
            "planned_candidates": sum(
                int(item.get("candidates_per_strategy") or 0) for item in strategies
            ),
            "neutral_residue_policy": (
                strategies[0].get("neutral_residue_policy") if strategies else None
            ),
        }
        tables["strategies"] = strategies[:200]
    elif stage_number == 4:
        progress = _optional_data(run_root, artifacts, "pilot-progress-final") or {}
        bundle = _optional_data(run_root, artifacts, "pilot-bundle") or {}
        highlights = {
            "strategy_count": bundle.get("strategy_count"),
            "planned_candidates": progress.get("planned_candidates"),
            "collected_candidates": progress.get("collected_candidates"),
            "elapsed_seconds": progress.get("elapsed_seconds"),
            "throughput_candidates_per_hour": progress.get("throughput_candidates_per_hour"),
            "succeeded_tasks": progress.get("succeeded_tasks"),
            "failed_tasks": progress.get("failed_tasks"),
        }
        tables["devices"] = [
            {"device": device, "current_strategy_id": value}
            for device, value in (progress.get("per_device") or {}).items()
        ]
    elif stage_number == 5:
        report = _optional_data(run_root, artifacts, "pilot-filter-report") or {}
        expansion = (
            _optional_data(run_root, artifacts, "advisory-validation-report")
            or _optional_data(run_root, artifacts, "expansion-validation-report")
            or {}
        )
        summaries = report.get("strategy_summaries") or []
        predictions = expansion.get("predictions") or []
        candidates = expansion.get("candidates") or []
        local_pass = sum(bool(item.get("local_gate_pass")) for item in candidates)
        binder_rmsd = [
            float(item["binder_pose_rmsd_angstrom"])
            for item in predictions
            if item.get("binder_pose_rmsd_angstrom") is not None
        ]
        target_rmsd = [
            float(item["target_ca_rmsd_angstrom"])
            for item in predictions
            if item.get("target_ca_rmsd_angstrom") is not None
        ]
        iptm = [
            float(item["pairwise_iptm"])
            for item in predictions
            if item.get("pairwise_iptm") is not None
        ]
        local_design_rmsd: list[float] = []
        for record in report.get("candidate_records") or []:
            for metric in record.get("metrics") or []:
                if metric.get("metric_id") == "filter-rmsd-design" and isinstance(
                    metric.get("value"), (int, float)
                ):
                    local_design_rmsd.append(float(metric["value"]))
        tier_counts: dict[str, int] = {}
        for item in summaries:
            tier = str(item.get("tier") or "unknown")
            tier_counts[tier] = tier_counts.get(tier, 0) + 1
        highlights = {
            "pilot_candidate_count": len(report.get("candidate_records") or []),
            "selected_strategy_count": len(
                report.get("promoted_strategy_ids")
                or report.get("selected_strategy_ids")
                or []
            ),
            "diagnostic_warning_count": len(expansion.get("warnings") or []),
            "tier_counts": tier_counts,
            "expanded_candidate_count": len(candidates),
            "local_gate_pass_count": local_pass,
            "protenix_prediction_count": len(predictions),
            "protenix_pass_count": sum(
                bool(item.get("structure_gate_pass", item.get("passed")))
                for item in predictions
            ),
            "status": expansion.get("status") or report.get("status"),
            "winner_strategy_id": expansion.get("winner_strategy_id"),
            "boltzgen_filter_rmsd_design_range": _number_range(local_design_rmsd),
            "boltzgen_filter_rmsd_design_median": (
                statistics.median(local_design_rmsd) if local_design_rmsd else None
            ),
            "protenix_target_rmsd_range": _number_range(target_rmsd),
            "protenix_binder_pose_rmsd_range": _number_range(binder_rmsd),
            "protenix_pairwise_iptm_range": _number_range(iptm),
        }
        tables["strategies"] = summaries
        tables["predictions"] = [
            {
                "candidate_id": item.get("candidate_id"),
                "target_ca_rmsd_angstrom": item.get("target_ca_rmsd_angstrom"),
                "binder_pose_rmsd_angstrom": item.get("binder_pose_rmsd_angstrom"),
                "pairwise_iptm": item.get("pairwise_iptm"),
                "minimum_interface_pae_angstrom": item.get(
                    "minimum_interface_pae_angstrom"
                ),
                "passed": item.get("structure_gate_pass", item.get("passed")),
            }
            for item in predictions
        ]
    elif stage_number == 6:
        plan = _optional_data(run_root, artifacts, "scale-plan") or {}
        progress = _optional_data(run_root, artifacts, "scale-progress-final") or {}
        strategy_allocations = plan.get("strategy_allocations") or []
        highlights = {
            "profile": plan.get("profile"),
            "requested_candidates": (
                plan.get("total_candidate_budget")
                or plan.get("requested_candidate_count")
            ),
            "allocation_policy": plan.get("allocation_policy"),
            "strategy_count": len(strategy_allocations) or 1,
            "shard_count": len(plan.get("shards") or []),
            "collected_candidates": progress.get("collected_candidates"),
            "elapsed_seconds": progress.get("elapsed_seconds"),
        }
        tables["strategy_allocations"] = strategy_allocations
        tables["shards"] = plan.get("shards") or []
    elif stage_number == 7:
        package = _optional_data(run_root, artifacts, "final-candidate-package") or {}
        report = _optional_data(run_root, artifacts, "final-filter-report") or {}
        primary = package.get("primary") or package.get("primary_candidates") or []
        backup = package.get("backup") or package.get("backup_candidates") or []
        sequence_prefilter = report.get("sequence_prefilter") or []
        deep_filter = report.get("deep_filter") or []
        predictions = report.get("predictions") or []
        consensus = report.get("consensus") or []
        highlights = {
            "status": package.get("status") or report.get("status"),
            "primary_count": len(primary),
            "backup_count": len(backup),
            "review_status": (
                package.get("human_review_status")
                or package.get("review_status")
            ),
            "tnp_status": (
                "complete"
                if primary or backup
                else package.get("tnp_status")
            ),
            "selection_scope": package.get("selection_scope"),
            "source_distribution": package.get("source_distribution") or [],
            "funnel": {
                "scale_candidates": len(sequence_prefilter),
                "sequence_hard_pass": sum(
                    bool(item.get("hard_pass")) for item in sequence_prefilter
                ),
                "deep_selected": len(deep_filter),
                "deep_gate_pass": sum(
                    bool(item.get("absolute_gate_pass")) for item in deep_filter
                ),
                "seed101_candidates": len(
                    {
                        item.get("candidate_id")
                        for item in predictions
                        if item.get("seed") == 101
                    }
                ),
                "multi_seed_consensus": sum(
                    bool(item.get("consensus_pass")) for item in consensus
                ),
                "selected_candidates": len(primary) + len(backup),
            },
        }
        tables["primary_candidates"] = primary
        tables["backup_candidates"] = backup
    return highlights, tables


def _state_for_manifest(manifest: StageManifest) -> UiStageState:
    artifact_ids = {item.artifact_id for item in manifest.output_artifacts}
    if any(item.endswith("scientific-stop") for item in artifact_ids):
        return UiStageState.SCIENTIFIC_STOP
    if manifest.status is ExecutionStatus.SUCCEEDED:
        return UiStageState.SUCCEEDED
    if manifest.status is ExecutionStatus.FAILED:
        return UiStageState.OPERATIONAL_FAILED
    if manifest.status is ExecutionStatus.RUNNING:
        return UiStageState.RUNNING
    return UiStageState.QUEUED


def get_run_projection(
    run_root: Path,
    *,
    registry: UiRunRegistry,
    signer: ArtifactTokenSigner,
    accepted_job_stage: int | None = None,
    accepted_job_at: datetime | None = None,
    accepted_job_status: str | None = None,
    projects_root: Path | None = None,
) -> RunProjection:
    """验证当前 manifest 链并生成不含绝对路径的 run 投影。"""

    root = run_root.resolve()
    run_key = registry.register(root)
    run_manifest, _ = _latest_run_manifest(root)
    stage_by_id = {ref.producer_stage: ref for ref in run_manifest.stage_manifest_refs}
    accepted_manifests = {
        int(str(stage_id).split("-", maxsplit=1)[0]): load_model(
            reference.verify(root),
            StageManifest,
        )
        for stage_id, reference in stage_by_id.items()
    }
    stages: list[StageProjection] = []
    highest = max(
        (int(str(stage_id).split("-", maxsplit=1)[0]) for stage_id in stage_by_id),
        default=0,
    )
    for index, (stage_id, title, capability) in enumerate(
        zip(STAGE_IDS, STAGE_TITLES, STAGE_CAPABILITIES, strict=True),
        start=1,
    ):
        stage_ref = stage_by_id.get(stage_id)
        if stage_ref is None:
            state = UiStageState.NOT_REACHED
            if accepted_job_stage == index:
                state = {
                    "queued": UiStageState.QUEUED,
                    "running": UiStageState.RUNNING,
                    "scientific-stop": UiStageState.SCIENTIFIC_STOP,
                    "operational-failed": UiStageState.OPERATIONAL_FAILED,
                    "failed": UiStageState.OPERATIONAL_FAILED,
                }.get(accepted_job_status or "", UiStageState.RUNNING)
            elif (
                index == highest + 1
                and run_manifest.status is ExecutionStatus.RUNNING
                and run_manifest.workflow_state is not None
            ):
                state = UiStageState.AWAITING_HUMAN_APPROVAL
            summary = (
                "执行已受理，配置已经冻结"
                if accepted_job_stage == index
                else "等待当前人工决策完成"
                if state is UiStageState.AWAITING_HUMAN_APPROVAL
                else "当前 run 未到达本阶段"
            )
            stages.append(
                StageProjection(
                    stage_number=index,
                    stage_id=stage_id,
                    title=title,
                    state=state,
                    capability=capability,
                    summary=summary,
                    evidence_status=str(run_manifest.evidence_status),
                    access=project_stage_access(
                        stage_number=index,
                        state=state,
                        stages=accepted_manifests,
                        accepted_job_stage=accepted_job_stage,
                        accepted_job_at=accepted_job_at,
                    ),
                )
            )
            continue
        stage_path = stage_ref.verify(root)
        manifest = load_model(stage_path, StageManifest)
        state = _state_for_manifest(manifest)
        highlights, tables = _stage_highlights(index, root, manifest)
        projected_artifacts = tuple(
            ArtifactProjection(
                artifact_id=item.artifact_id,
                role=item.role,
                file_format=item.file_format,
                size_bytes=item.size_bytes,
                sha256=item.sha256,
                token=signer.sign(run_key, item),
            )
            for item in manifest.output_artifacts
        )
        summary = (
            "软件正常完成，但科学门槛未通过"
            if state is UiStageState.SCIENTIFIC_STOP
            else f"{len(projected_artifacts)} 个 manifest-declared artifacts"
        )
        stages.append(
            StageProjection(
                stage_number=index,
                stage_id=stage_id,
                title=title,
                state=state,
                capability=capability,
                summary=summary,
                evidence_status=str(run_manifest.evidence_status),
                access=project_stage_access(
                    stage_number=index,
                    state=state,
                    stages=accepted_manifests,
                    accepted_job_stage=accepted_job_stage,
                    accepted_job_at=accepted_job_at,
                ),
                selected_attempt_id=manifest.selected_attempt_id,
                started_at=manifest.created_at,
                completed_at=manifest.completed_at,
                highlights=highlights,
                tables=tables,
                artifacts=projected_artifacts,
            )
        )
    code_identity = run_manifest.code_identity
    projection = RunProjection(
        run_key=run_key,
        project_id=run_manifest.project_id,
        run_id=run_manifest.run_id,
        status=str(run_manifest.status),
        evidence_status=str(run_manifest.evidence_status),
        workflow_state=(
            None
            if run_manifest.workflow_state is None
            else run_manifest.workflow_state.action
        ),
        created_at=run_manifest.created_at,
        updated_at=run_manifest.updated_at,
        completed_at=run_manifest.completed_at,
        code_version=(
            code_identity.version if code_identity is not None else run_manifest.easydesign_version
        ),
        code_commit=(
            code_identity.git_commit if code_identity is not None else run_manifest.code_commit
        ),
        profile_id=(
            None
            if run_manifest.runtime_profile is None
            else run_manifest.runtime_profile.profile_id
        ),
        integrity_status="verified",
        stages=tuple(stages),
    )
    if projects_root is None:
        return projection
    continuation = load_verified_project_scale_evidence(root, projects_root)
    if continuation is None:
        return projection
    projected_stages = list(projection.stages)
    stage05 = projected_stages[4]
    projected_stages[4] = stage05.model_copy(
        update={
            "state": UiStageState.SUCCEEDED,
            "summary": (
                "历史 v1.5 科学停止保持不变；v1.6 重评已晋级 "
                f"{len(continuation.policy_reevaluation.promoted_strategy_ids)} 个策略"
            ),
            "highlights": {
                **stage05.highlights,
                "historical_policy_status": str(stage05.state),
                "policy_reevaluation_profile": "nanobody-filter-standard-v1.6",
                "promoted_strategy_ids": list(
                    continuation.policy_reevaluation.promoted_strategy_ids
                ),
                "promotion_count": len(
                    continuation.policy_reevaluation.promoted_strategy_ids
                ),
                "diagnostic_warning_count": int(
                    bool(continuation.policy_reevaluation.promoted_strategy_ids)
                    and not stage05.highlights.get("protenix_pass_count")
                ),
                "status": continuation.policy_reevaluation.status,
                "policy_reevaluation_status": (
                    continuation.policy_reevaluation.status
                ),
            },
        }
    )
    execution = continuation.execution
    stage06 = projected_stages[5]
    projected_stages[5] = stage06.model_copy(
        update={
            "state": UiStageState.SUCCEEDED,
            "summary": (
                f"远端已完成 {execution.candidate_count:,} 个候选；"
                "通过不可变校验记录原地采用"
            ),
            "completed_at": execution.completed_at,
            "highlights": {
                "profile": "user-defined-v1",
                "requested_candidates": execution.candidate_count,
                "collected_candidates": execution.candidate_count,
                "strategy_count": len(execution.strategy_ids),
                "shard_count": execution.shard_count,
                "elapsed_seconds": execution.elapsed_seconds,
                "executor_id": execution.executor_id,
                "evidence_mode": "remote-in-place-adoption",
            },
            "tables": {
                "strategy_allocations": [
                    {
                        "strategy_id": strategy_id,
                        "requested_candidates": execution.strategy_candidate_counts[
                            strategy_id
                        ],
                    }
                    for strategy_id in execution.strategy_ids
                ],
                "devices": [
                    item.model_dump(mode="json")
                    for item in continuation.device_execution
                ],
            },
            "access": StageAccessProjection(
                stage_number=6,
                access="view-only",
                locked_by_stage=6,
                locked_at=execution.completed_at,
                reason="远端第6步已完成并由采用记录冻结",
                allowed_actions=("view-results", "download-evidence"),
            ),
        }
    )
    stage07 = projected_stages[6]
    projected_stages[6] = stage07.model_copy(
        update={
            "summary": "等待 Suzhou2 Protenix、TNP 与模型资产探针通过",
            "highlights": {
                **stage07.highlights,
                "readiness": continuation.stage07_readiness,
                "source_candidate_count": execution.candidate_count,
                "executor_id": execution.executor_id,
            },
            "access": StageAccessProjection(
                stage_number=7,
                access="view-only",
                locked_by_stage=6,
                locked_at=execution.completed_at,
                reason="第7步必须在远端后端探针通过后原地启动",
                allowed_actions=("view-requirements", "download-evidence"),
            ),
        }
    )
    return projection.model_copy(
        update={
            "updated_at": max(projection.updated_at, continuation.generated_at),
            "stages": tuple(projected_stages),
        }
    )


def get_stage_projection(
    run_root: Path,
    stage_number: int,
    *,
    registry: UiRunRegistry,
    signer: ArtifactTokenSigner,
    accepted_job_stage: int | None = None,
    accepted_job_at: datetime | None = None,
    accepted_job_status: str | None = None,
    projects_root: Path | None = None,
) -> StageProjection:
    if stage_number < 1 or stage_number > 7:
        raise ValueError("stage_number 必须在 1–7")
    return get_run_projection(
        run_root,
        registry=registry,
        signer=signer,
        accepted_job_stage=accepted_job_stage,
        accepted_job_at=accepted_job_at,
        accepted_job_status=accepted_job_status,
        projects_root=projects_root,
    ).stages[stage_number - 1]


def get_project_projection(
    project_id: str,
    *,
    registry: UiRunRegistry,
    signer: ArtifactTokenSigner,
    accepted_jobs: Mapping[
        str,
        tuple[int | None, datetime | None, str | None],
    ]
    | None = None,
    projects_root: Path | None = None,
) -> ProjectProjection:
    summaries = [item for item in list_runs(registry.runs_root) if item.project_id == project_id]
    projections = tuple(
        sorted(
            (
                get_run_projection(
                    item.path,
                    registry=registry,
                    signer=signer,
                    accepted_job_stage=(
                        None
                        if accepted_jobs is None
                        else accepted_jobs.get(
                            registry.register(item.path),
                            (None, None, None),
                        )[0]
                    ),
                    accepted_job_at=(
                        None
                        if accepted_jobs is None
                        else accepted_jobs.get(
                            registry.register(item.path),
                            (None, None, None),
                        )[1]
                    ),
                    accepted_job_status=(
                        None
                        if accepted_jobs is None
                        else accepted_jobs.get(
                            registry.register(item.path),
                            (None, None, None),
                        )[2]
                    ),
                    projects_root=projects_root,
                )
                for item in summaries
                if item.integrity_status == "verified"
            ),
            key=lambda item: item.updated_at,
            reverse=True,
        )
    )
    index = load_latest_runtime_model(
        registry.runs_root / "run-index.json",
        RunIndex,
    )
    primary_entries = [
        entry
        for entry in index.entries
        if entry.category == "project-run"
        and entry.project_id == project_id
        and entry.is_project_primary
    ]
    primary_projection = projections[0] if projections else None
    if primary_entries:
        primary_run_id = primary_entries[0].run_id
        primary_projection = next(
            (item for item in projections if item.run_id == primary_run_id),
            None,
        )
        if primary_projection is None:
            raise ManifestStateError(
                f"项目 {project_id} 的主展示运行不可验证: {primary_run_id}"
            )
    return ProjectProjection(
        project_id=project_id,
        run_count=len(projections),
        latest_run=primary_projection,
        runs=projections,
    )


def get_project_draft_projection(
    project_root: Path,
    *,
    session_id: str | None = None,
    session_updated_at: datetime | None = None,
) -> ProjectDraftProjection:
    """Project config is visible only after atomic publication."""

    root = project_root.resolve()
    pointer = root / "CONFIG_CURRENT"
    config_path = root / "easydesign.yaml"
    if pointer.is_file():
        relative = Path(read_last_text_line(pointer))
        if relative.is_absolute() or ".." in relative.parts:
            raise ManifestStateError("项目 CONFIG_CURRENT 不是项目内相对路径")
        config_path = (root / relative).resolve()
        try:
            config_path.relative_to(root)
        except ValueError as error:
            raise ManifestStateError("项目配置逃出项目目录") from error
    try:
        payload = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, yaml.YAMLError) as error:
        raise ManifestStateError(f"无法读取项目草稿配置: {root.name}") from error
    if not isinstance(payload, dict):
        raise ManifestStateError("项目草稿配置不是 YAML object")
    project_id = str(payload.get("project_id") or root.name)
    stage01 = payload.get("stage01") or {}
    target = stage01.get("target") or {}
    source = target.get("source") or {}
    input_type = str(source.get("type") or source.get("format") or "unknown")
    configured = max(
        (
            number
            for number in range(1, 8)
            if payload.get(f"stage{number:02d}") is not None
        ),
        default=1,
    )
    modified_at = datetime.fromtimestamp(config_path.stat().st_mtime, tz=UTC)
    metadata_path = root / "project-metadata.json"
    if metadata_path.is_file():
        try:
            metadata = load_latest_runtime_model(metadata_path, ProjectMetadata)
        except (OSError, ValueError) as error:
            raise ManifestStateError(
                f"项目元数据不可验证: {root.name}"
            ) from error
        if metadata.project_id != project_id:
            raise ManifestStateError("项目元数据与配置 project_id 不一致")
        if metadata.config_sha256 == sha256_file(config_path):
            input_type = metadata.input_type
            configured = metadata.configured_through_stage
            modified_at = metadata.updated_at
    updated_at = max(
        value
        for value in (modified_at, session_updated_at)
        if value is not None
    )
    return ProjectDraftProjection(
        project_id=project_id,
        target_id=str(target.get("id") or "未命名目标"),
        input_type=input_type,
        configured_through_stage=configured,
        updated_at=updated_at,
        config_sha256=sha256_file(config_path),
        session_id=session_id,
    )


def create_demo_replay(run_root: Path, *, registry: UiRunRegistry) -> ReplayTimeline:
    """从真实终态 manifest 构造明确标记的 UI-only 演示时间线。"""

    root = run_root.resolve()
    run_key = registry.register(root)
    manifest, _ = _latest_run_manifest(root)
    completed: set[int] = set()
    scientific_stops: set[int] = set()
    for stage_ref in manifest.stage_manifest_refs:
        stage_number = int(str(stage_ref.producer_stage).split("-", maxsplit=1)[0])
        completed.add(stage_number)
        stage_manifest = load_model(stage_ref.verify(root), StageManifest)
        if _state_for_manifest(stage_manifest) is UiStageState.SCIENTIFIC_STOP:
            scientific_stops.add(stage_number)
    frames: list[ReplayFrame] = [
        ReplayFrame(
            frame_id="replay-start",
            label="案例已载入",
            stage_number=None,
            state=UiStageState.SIMULATED_PREVIEW,
            description="审计证据保持只读；以下中间状态为产品回放。",
        )
    ]
    for number in range(1, 8):
        if number in completed:
            frames.extend(
                (
                    ReplayFrame(
                        frame_id=f"stage-{number:02d}-running",
                        label=f"Stage {number:02d} 运行中",
                        stage_number=number,
                        state=UiStageState.SIMULATED_PREVIEW,
                        description="回放状态，不代表新 backend 正在运行。",
                    ),
                    ReplayFrame(
                        frame_id=f"stage-{number:02d}-complete",
                        label=f"Stage {number:02d} 已完成",
                        stage_number=number,
                        state=(
                            UiStageState.SCIENTIFIC_STOP
                            if number in scientific_stops
                            else UiStageState.SUCCEEDED
                        ),
                        description=(
                            "软件完成并发布可审计科学停止。"
                            if number in scientific_stops
                            else "读取真实终态 evidence。"
                        ),
                    ),
                )
            )
        else:
            frames.append(
                ReplayFrame(
                    frame_id=f"stage-{number:02d}-not-reached",
                    label=f"Stage {number:02d} 未到达",
                    stage_number=number,
                    state=UiStageState.NOT_REACHED,
                    description="当前 source run 没有该阶段的正式 StageManifest。",
                )
            )
    return ReplayTimeline(
        replay_id=f"replay-{run_key}",
        source_run_key=run_key,
        source_manifest_sha256=canonical_model_sha256(manifest),
        frames=tuple(frames),
    )


def stream_run_events(run_root: Path) -> Iterator[str]:
    """只流式读取当前 StageManifest 声明的 append-only event artifact。"""

    root = run_root.resolve()
    manifest, _ = _latest_run_manifest(root)
    for stage_ref in reversed(manifest.stage_manifest_refs):
        stage_manifest = load_model(stage_ref.verify(root), StageManifest)
        event_ref = next(
            (
                item
                for item in stage_manifest.output_artifacts
                if item.role == "append-only-task-events"
            ),
            None,
        )
        if event_ref is None:
            continue
        path = event_ref.verify(root)
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                value = line.strip()
                if value:
                    yield value
        return


def create_draft_order_package(
    run_root: Path,
    *,
    registry: UiRunRegistry,
    signer: ArtifactTokenSigner,
) -> DraftOrderOutcome:
    """仅在真实 Stage 07 FinalCandidatePackage 存在时授权下载既有人工审核包。"""

    stage = get_stage_projection(
        run_root,
        7,
        registry=registry,
        signer=signer,
    )
    if stage.state is not UiStageState.SUCCEEDED:
        return DraftOrderOutcome(
            status="not-available",
            allowed=False,
            reason="当前 run 没有成功发布 FinalCandidatePackage；不能生成下单草案。",
            candidate_count=0,
        )
    package = next(
        (item for item in stage.artifacts if item.artifact_id == "final-candidate-package"),
        None,
    )
    if package is None:
        return DraftOrderOutcome(
            status="not-available",
            allowed=False,
            reason="Stage 07 未声明 final-candidate-package。",
            candidate_count=0,
        )
    primary = stage.tables.get("primary_candidates", [])
    backup = stage.tables.get("backup_candidates", [])
    return DraftOrderOutcome(
        status="draft-ready",
        allowed=True,
        reason="只提供人工审核包；不会调用供应商或发送订单。",
        candidate_count=len(primary) + len(backup),
        package_token=package.token,
    )


def utc_now() -> datetime:
    return datetime.now(tz=UTC)


__all__ = [
    "ArtifactTokenSigner",
    "UiRunRegistry",
    "create_demo_replay",
    "create_draft_order_package",
    "get_project_projection",
    "get_run_projection",
    "get_stage_projection",
    "stream_run_events",
]
