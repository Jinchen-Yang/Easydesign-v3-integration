"""Typed project-centric commands for the permanent VS Code product."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]
from pydantic import BaseModel, ConfigDict, Field

from easydesign.backends.executors import NvidiaSmiProbe
from easydesign.core import ConfigurationError, RunManifest, StageManifest, load_model
from easydesign.safe_writes import read_last_text_line
from easydesign.stages.s02_hotspot_discovery import RegionMethod
from easydesign.workspace_context import WorkspaceContext

from .config import Stage02Config
from .decisions import approve_decision, export_decision
from .hotspots import approve_hotspots, export_hotspot_review
from .local_jobs import ACTIVE_JOB_STATUSES, LocalStepJob, LocalStepJobController
from .local_project import (
    STAGE_FILENAMES,
    bind_project_run,
    completed_config_matches,
    completed_steps,
    compose_config,
    initialize_local_project,
    project_config_path,
    publish_config_revision,
    read_stage_fragment,
    resolve_project_path,
    resolve_project_run,
    validate_composed_config,
)


class StepCommandResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    status: str
    project_id: str
    run_id: str | None = None
    step: int | None = Field(default=None, ge=1, le=7)
    job_id: str | None = None
    run_root: Path | None = None
    manifest: Path | None = None
    generated_files: tuple[Path, ...] = ()
    next_actions: tuple[str, ...] = ()


def _project_id(root: Path) -> str:
    from .config import load_run_config

    return load_run_config(
        project_config_path(root), source_base_dir=root
    ).config.project_id


def initialize_step_project(**values: Any) -> StepCommandResult:
    initialized = initialize_local_project(**values)
    root = initialized.project_root
    files = tuple(root / STAGE_FILENAMES[step] for step in range(1, 8)) + (
        initialized.config_path,
        root / "CONFIG_CURRENT",
        root / "inputs",
    )
    return StepCommandResult(
        status="initialized",
        project_id=_project_id(root),
        step=1,
        generated_files=files,
        next_actions=(
            f"检查 {root / STAGE_FILENAMES[1]}",
            f"easydesign step validate 1 {root}",
            f"easydesign step run 1 {root}",
        ),
    )


def stage_template(
    step: int,
    project_root: Path,
    *,
    manual: bool = False,
    output: Path | None = None,
) -> StepCommandResult:
    root = resolve_project_path(project_root, must_exist=True)
    if step != 2 or not manual:
        selected = root / STAGE_FILENAMES[step]
        return StepCommandResult(
            status="template-ready",
            project_id=_project_id(root),
            step=step,
            generated_files=(selected,),
            next_actions=(f"编辑 {selected}",),
        )
    destination = (
        root / "02-hotspot-discovery.manual.yaml"
        if output is None
        else (output if output.is_absolute() else root / output)
    ).resolve()
    if not destination.is_relative_to(root):
        raise ConfigurationError("手动区域模板必须位于当前项目目录")
    template = Stage02Config.model_validate(
        {
            "mode": "user-provided",
            "methods": [],
            "automatic": None,
            "annotations": {"uniprot": "if_available"},
            "user_regions": {
                "source": {
                    "type": "residue-list",
                    "numbering": "label",
                    "regions": [
                        {"id": "A", "residues": ["10", "11", "12"]},
                        {"id": "B", "residues": ["40", "41", "42"]},
                        {"id": "C", "residues": ["70", "71", "72"]},
                    ],
                }
            },
        }
    )
    with destination.open("x", encoding="utf-8", newline="\n") as handle:
        yaml.safe_dump(
            template.model_dump(mode="json", exclude_none=False),
            handle,
            allow_unicode=True,
            sort_keys=False,
        )
    return StepCommandResult(
        status="template-created",
        project_id=_project_id(root),
        step=step,
        generated_files=(destination,),
        next_actions=(
            f"编辑 label residue IDs: {destination}",
            f"easydesign step validate 2 {root} --config {destination}",
            f"easydesign step run 2 {root} --config {destination}",
        ),
    )


def validate_step(
    step: int,
    project_root: Path,
    *,
    config_path: Path | None = None,
    run_id: str | None = None,
) -> StepCommandResult:
    root = resolve_project_path(project_root, must_exist=True)
    summary = resolve_project_run(root, run_id=run_id, required=False)
    fragment = read_stage_fragment(step, root, custom_path=config_path)
    composed = compose_config(
        step,
        root,
        fragment=fragment,
        run_root=None if summary is None else summary.path,
    )
    validate_composed_config(root, composed)
    return StepCommandResult(
        status="valid",
        project_id=composed.project_id,
        run_id=None if summary is None else summary.run_id,
        step=step,
        run_root=None if summary is None else summary.path,
        manifest=None if summary is None else summary.latest_manifest,
        next_actions=(f"easydesign step run {step} {root}",),
    )


def _resource_actions(step: int, config: BaseModel) -> tuple[str, ...]:
    context = WorkspaceContext.discover()
    disk = shutil.disk_usage(context.root)
    try:
        snapshots = NvidiaSmiProbe().snapshots()
        gpu_text = "; ".join(
            f"GPU {item.device}: memory={item.memory_used_mib}MiB, "
            f"util={item.utilization_percent}%, pids={list(item.compute_process_pids)}"
            for item in snapshots
        ) or "没有检测到 GPU"
    except Exception as error:
        gpu_text = f"GPU probe 不可用: {type(error).__name__}: {error}"
    payload = config.model_dump(mode="json")
    if step == 4:
        budget = f"每个策略 {payload['required_complete_candidates_per_strategy']} 个 pilot 候选"
        backends = "boltzgen"
    elif step == 5:
        advisory = payload.get("advisory_validation", {})
        budget = (
            f"每策略 expansion={advisory.get('expanded_total_per_strategy')}, "
            f"full-target refold={advisory.get('full_target_refold_top_n')}"
        )
        backends = "boltzgen + protenix-v2"
    elif step == 6:
        budget = f"总候选数 {payload['total_candidate_count']}"
        backends = "boltzgen"
    else:
        budget = (
            f"primary={payload['primary_count']}, backup={payload['backup_count']}, "
            f"TNP required={payload['tnp_required']}"
        )
        backends = "protenix-v2 + tnp"
    return (
        f"规范科学预算: {budget}",
        f"所需 backend: {backends}",
        gpu_text,
        f"磁盘可用 {disk.free / 1024**3:.1f} GiB；安全余量 10 GiB",
        f"确认后执行: easydesign step run {step} PROJECT --confirm",
    )


def _current_manifest(run_root: Path) -> tuple[RunManifest, Path]:
    name = read_last_text_line(run_root / "manifests/LATEST")
    path = run_root / "manifests" / name
    return load_model(path, RunManifest), path


def _stage02_is_approved(run_root: Path) -> bool:
    run, _ = _current_manifest(run_root)
    for reference in run.stage_manifest_refs:
        if reference.producer_stage != "02-hotspot-discovery":
            continue
        stage = load_model(reference.verify(run_root), StageManifest)
        return any(item.artifact_id == "hotspots" for item in stage.output_artifacts)
    return False


def _stage02_templates(project_root: Path, run_root: Path) -> tuple[Path, ...]:
    run, _ = _current_manifest(run_root)
    stage_ref = next(
        (
            item
            for item in run.stage_manifest_refs
            if item.producer_stage == "02-hotspot-discovery"
        ),
        None,
    )
    if stage_ref is None:
        return ()
    stage = load_model(stage_ref.verify(run_root), StageManifest)
    ids = {item.artifact_id for item in stage.output_artifacts}
    generated: list[Path] = []
    options = (
        (
            "sasa",
            RegionMethod.SASA_SURFACE_DIVERSITY,
            "sasa-recommended-regions",
        ),
        (
            "scannet",
            RegionMethod.SCANNET_EPITOPE_NO_MSA,
            "scannet-recommended-regions",
        ),
    )
    for label, method, artifact_id in options:
        if artifact_id not in ids:
            continue
        output = project_root / f"02-approval.{label}.{run.run_id}.yaml"
        if not output.exists():
            export_hotspot_review(run_root, method=method, output=output)
        generated.append(output)
    if "user-provided-regions" in ids:
        output = project_root / f"02-approval.manual.{run.run_id}.yaml"
        if not output.exists():
            export_hotspot_review(run_root, output=output)
        generated.append(output)
    return tuple(generated)


def _guidance(
    *,
    status: str,
    step: int,
    project_root: Path,
    run_id: str | None,
    generated: tuple[Path, ...] = (),
) -> tuple[str, ...]:
    if run_id is None:
        return ()
    viewer = f"easydesign step view {project_root} --run {run_id} --port 8000"
    if status == "awaiting-human-approval" and step == 1:
        decisions = tuple(
            path for path in generated if path.name.startswith("01-decision.")
        )
        return tuple(
            f"编辑后批准: easydesign step approve 1 {project_root} --input {path}"
            for path in decisions
        )
    if status == "awaiting-human-approval" and step == 2:
        approvals = tuple(
            path for path in generated if path.name.startswith("02-approval.")
        )
        return (
            viewer,
            "浏览器访问 http://127.0.0.1:8000/（只读）",
            *tuple(
                f"填写审批模板后运行: easydesign step approve 2 {project_root} --input {p}"
                for p in approvals
            ),
        )
    if status != "succeeded":
        return (f"检查任务状态: easydesign step status {project_root} --run {run_id}",)
    if step == 1:
        return (
            viewer,
            "浏览器访问 http://127.0.0.1:8000/（只读）",
            f"自动 SASA + ScanNet: easydesign step run 2 {project_root}",
            f"生成人工区域模板: easydesign step template 2 {project_root} --manual",
        )
    if step < 7:
        return (f"下一步: easydesign step run {step + 1} {project_root}",)
    return ("Stage 07 已完成；结果以 manifest 和正式 artifact 为准。",)


def _result_from_job(
    job: LocalStepJob,
    *,
    generated: tuple[Path, ...] = (),
) -> StepCommandResult:
    return StepCommandResult(
        status=job.status,
        project_id=job.project_id,
        run_id=job.run_id,
        step=job.step,
        job_id=job.job_id,
        run_root=job.run_root,
        manifest=job.run_manifest,
        generated_files=generated,
        next_actions=_guidance(
            status=job.status,
            step=job.step,
            project_root=job.project_root,
            run_id=job.run_id,
            generated=generated,
        ),
    )


def _wait_or_detach(
    controller: LocalStepJobController,
    job: LocalStepJob,
    *,
    detach: bool,
) -> LocalStepJob:
    if detach:
        return job.model_copy(update={"status": "detached"})
    try:
        return controller.wait(job.job_id)
    except KeyboardInterrupt:
        # The worker owns the science process session.  Ctrl-C only stops this
        # observer and must never signal the worker.
        current = controller.load(job.job_id)
        return current.model_copy(update={"status": "detached"})


def run_step(
    step: int,
    project_root: Path,
    *,
    config_path: Path | None = None,
    run_id: str | None = None,
    confirm: bool = False,
    detach: bool = False,
) -> StepCommandResult:
    root = resolve_project_path(project_root, must_exist=True)
    project_id = _project_id(root)
    summary = resolve_project_run(root, run_id=run_id, required=False)
    fragment = read_stage_fragment(step, root, custom_path=config_path)
    if summary is not None:
        completed = completed_steps(summary.path)
        if step in completed:
            if not completed_config_matches(summary.path, step, fragment):
                raise ConfigurationError(
                    "已完成 Stage 的配置已变化，拒绝原地覆盖；请显式初始化新项目/run"
                )
            no_op_status = (
                "awaiting-human-approval"
                if step == 2 and not _stage02_is_approved(summary.path)
                else "no-op"
            )
            no_op_generated = (
                _stage02_templates(root, summary.path)
                if no_op_status == "awaiting-human-approval"
                else ()
            )
            return StepCommandResult(
                status=no_op_status,
                project_id=project_id,
                run_id=summary.run_id,
                step=step,
                run_root=summary.path,
                manifest=summary.latest_manifest,
                generated_files=no_op_generated,
                next_actions=_guidance(
                    status=no_op_status if no_op_status != "no-op" else "succeeded",
                    step=step,
                    project_root=root,
                    run_id=summary.run_id,
                    generated=no_op_generated,
                ),
            )
        expected = 1 if not completed else max(completed) + 1
        if step != expected:
            raise ConfigurationError(f"当前 run 下一阶段必须是 Stage {expected:02d}")
        if step > 2 and summary.status != "succeeded":
            raise ConfigurationError(
                "上游 run 尚未形成 succeeded 终态；Stage 02 必须先完成显式 approve"
            )
    elif step != 1:
        raise ConfigurationError("新项目必须先运行 Stage 01")
    composed = compose_config(
        step,
        root,
        fragment=fragment,
        run_root=None if summary is None else summary.path,
    )
    validate_composed_config(root, composed)
    if step >= 4 and not confirm:
        return StepCommandResult(
            status="confirmation-required",
            project_id=project_id,
            run_id=None if summary is None else summary.run_id,
            step=step,
            run_root=None if summary is None else summary.path,
            manifest=None if summary is None else summary.latest_manifest,
            next_actions=_resource_actions(step, fragment),
        )
    revision = publish_config_revision(root, composed)
    controller = LocalStepJobController()
    job = controller.launch(
        operation="run",
        project_id=project_id,
        project_root=root,
        step=step,
        config_path=revision,
        run_id=None if summary is None else summary.run_id,
        run_root=None if summary is None else summary.path,
    )
    observed = _wait_or_detach(controller, job, detach=detach)
    generated: tuple[Path, ...] = (revision,)
    if observed.status != "detached" and observed.run_root is not None:
        if observed.status == "awaiting-human-approval" and step == 1:
            decision = root / f"01-decision.{observed.run_id}.yaml"
            if not decision.exists():
                export_decision(observed.run_root, output=decision)
            generated += (decision,)
        elif observed.status == "awaiting-human-approval" and step == 2:
            generated += _stage02_templates(root, observed.run_root)
    return _result_from_job(observed, generated=generated)


def approve_step(
    step: int,
    project_root: Path,
    *,
    input_path: Path,
    run_id: str | None = None,
    detach: bool = False,
) -> StepCommandResult:
    root = resolve_project_path(project_root, must_exist=True)
    summary = resolve_project_run(root, run_id=run_id, required=True)
    assert summary is not None
    selected_input = input_path.expanduser().resolve(strict=True)
    if step == 1:
        record = approve_decision(summary.path, input_path=selected_input)
        controller = LocalStepJobController()
        job = controller.launch(
            operation="decision",
            project_id=summary.project_id,
            project_root=root,
            step=1,
            decision_record=record,
            run_id=summary.run_id,
            run_root=summary.path,
        )
        observed = _wait_or_detach(controller, job, detach=detach)
        return _result_from_job(observed, generated=(record,))
    if step != 2:
        raise ConfigurationError("step approve 只支持 Stage 01 decision 或 Stage 02 hotspots")
    hotspots = approve_hotspots(summary.path, input_path=selected_input)
    binding = bind_project_run(root, summary.path)
    _run, manifest = _current_manifest(summary.path)
    return StepCommandResult(
        status="succeeded",
        project_id=summary.project_id,
        run_id=binding.run_id,
        step=2,
        run_root=summary.path,
        manifest=manifest,
        generated_files=(hotspots,),
        next_actions=_guidance(
            status="succeeded",
            step=2,
            project_root=root,
            run_id=binding.run_id,
        ),
    )


def status_step(project_root: Path, *, run_id: str | None = None) -> StepCommandResult:
    root = resolve_project_path(project_root, must_exist=True)
    project_id = _project_id(root)
    controller = LocalStepJobController()
    job = controller.latest(project_id)
    summary = resolve_project_run(root, run_id=run_id, required=False)
    if job is not None and (run_id is None or job.run_id == run_id) and (
        job.status in ACTIVE_JOB_STATUSES
        or summary is None
        or job.run_manifest == summary.latest_manifest
    ):
        return _result_from_job(job)
    if summary is None:
        return StepCommandResult(status="not-started", project_id=project_id)
    completed = completed_steps(summary.path)
    return StepCommandResult(
        status=summary.status,
        project_id=project_id,
        run_id=summary.run_id,
        step=max(completed) if completed else 1,
        run_root=summary.path,
        manifest=summary.latest_manifest,
    )


def watch_step(project_root: Path, *, run_id: str | None = None) -> StepCommandResult:
    root = resolve_project_path(project_root, must_exist=True)
    controller = LocalStepJobController()
    job = controller.latest(_project_id(root))
    if job is None or (run_id is not None and job.run_id != run_id):
        raise ConfigurationError("项目没有匹配的 local job")
    return _result_from_job(_wait_or_detach(controller, job, detach=False))


def resume_step(
    project_root: Path,
    *,
    run_id: str | None = None,
    detach: bool = False,
) -> StepCommandResult:
    root = resolve_project_path(project_root, must_exist=True)
    summary = resolve_project_run(root, run_id=run_id, required=True)
    assert summary is not None
    controller = LocalStepJobController()
    latest = controller.latest(summary.project_id)
    if latest is not None and latest.status in ACTIVE_JOB_STATUSES:
        return _result_from_job(_wait_or_detach(controller, latest, detach=detach))
    if summary.status != "running":
        raise ConfigurationError("只有 manifest 状态为 running 的长任务 run 可以 resume")
    completed = completed_steps(summary.path)
    step = max(completed, default=0) + 1
    if step not in {4, 5, 6, 7}:
        raise ConfigurationError("当前 run 没有可恢复的 Stage 04–07 长任务")
    job = controller.launch(
        operation="resume",
        project_id=summary.project_id,
        project_root=root,
        step=step,
        run_id=summary.run_id,
        run_root=summary.path,
    )
    return _result_from_job(_wait_or_detach(controller, job, detach=detach))


def drain_step(project_root: Path, *, job_id: str | None = None) -> StepCommandResult:
    root = resolve_project_path(project_root, must_exist=True)
    controller = LocalStepJobController()
    job = controller.latest(_project_id(root)) if job_id is None else controller.load(job_id)
    if job is None:
        raise ConfigurationError("项目没有 local job")
    return _result_from_job(controller.request_drain(job.job_id))


__all__ = [
    "StepCommandResult",
    "approve_step",
    "drain_step",
    "initialize_step_project",
    "resume_step",
    "run_step",
    "stage_template",
    "status_step",
    "validate_step",
    "watch_step",
]
