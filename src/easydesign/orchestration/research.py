"""Agent-native research façade over the internal seven-stage science engine."""

from __future__ import annotations

import json
import os
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, Self, cast
from uuid import uuid4

import yaml  # type: ignore[import-untyped]
from pydantic import BaseModel, ConfigDict, Field, model_validator

from easydesign.backends.boltzgen import BoltzGenCheckAdapter
from easydesign.backends.executors import NvidiaSmiProbe
from easydesign.core import (
    ArtifactRef,
    ConfigurationError,
    RunManifest,
    StageManifest,
    load_model,
    sha256_file,
)
from easydesign.safe_writes import read_last_text_line
from easydesign.stages.s02_hotspot_discovery import HotspotsFile, RegionMethod
from easydesign.stages.s03_boltzgen_configuration import (
    SCAFFOLD_IDS,
    ExplicitStrategyVariant,
    NativeStrategyVariant,
    compile_vhh_strategy_plan,
)
from easydesign.stages.s03_boltzgen_configuration import (
    CdrOverride as CompiledCdrOverride,
)
from easydesign.stages.s03_boltzgen_configuration import (
    TargetCrop as CompiledTargetCrop,
)
from easydesign.workspace_context import WorkspaceContext

from .application import RunSummary, list_runs
from .config import (
    EasyDesignRunConfig,
    Stage02Config,
    Stage03Config,
    Stage04Config,
    Stage05Config,
    Stage06Config,
    Stage07Config,
    load_run_config,
)
from .decisions import approve_decision, export_decision
from .hotspots import approve_hotspots, export_hotspot_review
from .local_jobs import (
    ACTIVE_JOB_STATUSES,
    LocalStepJob,
    LocalStepJobController,
    wait_or_detach,
)
from .local_project import (
    STAGE_FILENAMES,
    bind_project_run,
    completed_steps,
    project_config_path,
    publish_config_revision,
    resolve_project_path,
)
from .profile import load_runtime_profile
from .project import InitializedProject, initialize_project
from .research_models import CommandResult, EvidenceItem, NextAction, ResearchPhase
from .workspace import load_resolved_run_config

SITE_POINTER = "SITE_CURRENT"
STRATEGY_POINTER = "STRATEGY_CURRENT"
PROMOTION_POINTER = "PROMOTION_CURRENT"
ExperimentRole = Literal[
    "baseline",
    "diagnostic",
    "integrated-alternative",
    "confirmatory",
]
FIRST_PILOT_SCAFFOLD_COUNT = 7
FIRST_PILOT_CANDIDATES_PER_GROUP = 40


class ProjectDescriptor(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["1.0"] = "1.0"
    product: Literal["easydesign-local"] = "easydesign-local"
    project_id: str
    target_id: str
    source_type: str
    created_at: datetime


class TargetCrop(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    start: int = Field(ge=1)
    end: int = Field(ge=1)

    @model_validator(mode="after")
    def ordered(self) -> Self:
        if self.end < self.start:
            raise ValueError("target crop end 不能小于 start")
        return self


class CdrOverride(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    cdr: Literal[1, 2, 3]
    design_res_index: str = Field(pattern=r"^[0-9]+(?:\.\.[0-9]+)?(?:,[0-9]+(?:\.\.[0-9]+)?)*$")
    insertion_num_residues: str = Field(pattern=r"^[0-9]+(?:\.\.[0-9]+)?$")


class StrategyVariant(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]{0,63}$")
    hotspot_set_id: str | None = None
    binding_label_seq_ids: tuple[int, ...] | None = None
    scaffold_ids: tuple[str, ...] = SCAFFOLD_IDS
    target_crop: TargetCrop | None = None
    cdr_overrides: tuple[CdrOverride, ...] = ()
    candidates: int = Field(default=40, ge=1)
    native_boltzgen_yaml: Path | None = None
    native_boltzgen_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    hypothesis_id: str | None = Field(
        default=None,
        pattern=r"^[a-z0-9][a-z0-9._-]{0,63}$",
    )
    role: ExperimentRole | None = None
    evidence_refs: tuple[str, ...] = ()
    changed_factors: tuple[str, ...] = ()
    held_constant: tuple[str, ...] = ()
    rationale: str = Field(min_length=1, max_length=4096)
    expected_result: str = Field(min_length=1, max_length=4096)
    failure_interpretation: str | None = Field(default=None, min_length=1, max_length=4096)

    @model_validator(mode="after")
    def validate_variant(self) -> Self:
        if len(self.scaffold_ids) != len(set(self.scaffold_ids)):
            raise ValueError("scaffold_ids 不能重复")
        unknown = sorted(set(self.scaffold_ids) - set(SCAFFOLD_IDS))
        if unknown:
            raise ValueError(f"未知 scaffold: {unknown}")
        if self.binding_label_seq_ids is not None:
            values = tuple(sorted(set(self.binding_label_seq_ids)))
            if values != self.binding_label_seq_ids or any(item < 1 for item in values):
                raise ValueError("binding_label_seq_ids 必须升序、唯一且为正整数")
        if self.native_boltzgen_yaml is None:
            if self.hotspot_set_id is None and self.binding_label_seq_ids is None:
                raise ValueError("普通 variant 必须选择 hotspot_set_id 或 binding residues")
        elif self.hotspot_set_id is not None or self.binding_label_seq_ids is not None:
            raise ValueError("native BoltzGen variant 不能同时声明 EasyDesign binding 选择")
        elif len(self.scaffold_ids) != 1:
            raise ValueError("native BoltzGen variant 必须声明且仅声明一个 provenance scaffold")
        elif self.native_boltzgen_sha256 is None:
            raise ValueError("native BoltzGen variant 必须记录 source SHA-256")
        cdrs = [item.cdr for item in self.cdr_overrides]
        if len(cdrs) != len(set(cdrs)):
            raise ValueError("同一 CDR 只能覆盖一次")
        for field_name in ("evidence_refs", "changed_factors", "held_constant"):
            items = getattr(self, field_name)
            if any(not item.strip() for item in items):
                raise ValueError(f"{field_name} 不能包含空值")
            if len(items) != len(set(items)):
                raise ValueError(f"{field_name} 不能重复")
        return self

    def has_complete_experiment_contract(self) -> bool:
        return bool(
            self.hypothesis_id
            and self.role
            and self.evidence_refs
            and self.changed_factors
            and self.held_constant
            and self.failure_interpretation
        )


class ResearchStrategy(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["1.0", "1.1"] = "1.1"
    foundation: Literal["current"] | str = "current"
    variants: tuple[StrategyVariant, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_variants(self) -> Self:
        ids = [item.id for item in self.variants]
        if len(ids) != len(set(ids)):
            raise ValueError("strategy variant id 不能重复")
        if self.schema_version == "1.1":
            incomplete = [
                item.id for item in self.variants if not item.has_complete_experiment_contract()
            ]
            if incomplete:
                raise ValueError(
                    f"schema 1.1 variant 必须记录完整 experiment contract: {incomplete}"
                )
        return self


class PromotionReceipt(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["1.0"] = "1.0"
    selection_id: str
    project_id: str
    pilot_run_id: str
    pilot_manifest_sha256: str
    strategy_ids: tuple[str, ...] = Field(min_length=1)
    approved_at: datetime


def _exclusive_yaml(model: BaseModel | dict[str, Any], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = model.model_dump(mode="json") if isinstance(model, BaseModel) else model
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        yaml.safe_dump(payload, handle, allow_unicode=True, sort_keys=False)
        handle.flush()
        os.fsync(handle.fileno())
    return path


def _exclusive_text(text: str, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
        handle.flush()
        os.fsync(handle.fileno())
    return path


def _replace_yaml(model: BaseModel | dict[str, Any], path: Path) -> Path:
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    _exclusive_yaml(model, temporary)
    os.replace(temporary, path)
    return path


def _append_pointer(project_root: Path, name: str, relative: Path) -> None:
    if relative.is_absolute() or ".." in relative.parts:
        raise ConfigurationError(f"{name} 必须引用项目内相对路径")
    path = project_root / name
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(relative.as_posix() + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def _read_pointer(project_root: Path, name: str) -> Path | None:
    pointer = project_root / name
    if not pointer.is_file():
        return None
    relative = Path(read_last_text_line(pointer))
    if relative.is_absolute() or ".." in relative.parts:
        raise ConfigurationError(f"{name} 指针无效")
    selected = (project_root / relative).resolve(strict=True)
    if not selected.is_relative_to(project_root):
        raise ConfigurationError(f"{name} 逃出项目目录")
    return selected


def _source_type(config: EasyDesignRunConfig) -> str:
    return str(config.stage01.target.source.type)


def initialize_research_project(**values: Any) -> CommandResult:
    requested = values.pop("project_root")
    root = resolve_project_path(requested, must_exist=False)
    source_run_root = values.get("source_run_root")
    if source_run_root is not None:
        context = WorkspaceContext.discover()
        source = Path(source_run_root).expanduser().resolve(strict=True)
        example = (context.root / "examples/apoe-ui-demo").resolve(strict=False)
        if not (source.is_relative_to(context.runs_root) or source.is_relative_to(example)):
            raise ConfigurationError(
                "拒绝读取旧 UI 或外部 run；只允许 local run 或 Git APOE evidence"
            )
    initialized: InitializedProject = initialize_project(
        project_root=root,
        stop_after_stage=7,
        stage02_method="both",
        execution_mode="review-gated",
        **values,
    )
    try:
        full = load_run_config(initialized.config_path, source_base_dir=root).config
        payload = full.model_dump(mode="python", exclude_none=False)
        payload["workflow"]["stop_after_stage"] = 1
        for step in range(2, 8):
            payload[f"stage{step:02d}"] = None
        initial = EasyDesignRunConfig.model_validate(payload)
        initialized.config_path.unlink()
        gitignore = root / ".gitignore"
        if gitignore.is_file():
            gitignore.unlink()
        revision = publish_config_revision(root, initial)
        (root / "strategies").mkdir()
        descriptor = ProjectDescriptor(
            project_id=initial.project_id,
            target_id=initial.stage01.target.target_id,
            source_type=_source_type(initial),
            created_at=datetime.now(UTC),
        )
        descriptor_path = _exclusive_yaml(descriptor, root / "PROJECT.yaml")
        decisions = _exclusive_text(
            "# Research decisions\n\n"
            "候选经验必须记录适用范围、证据 run、反例、置信度、审核人和日期；"
            "研究者批准后才能发布到正式 Skill。\n",
            root / "DECISIONS.md",
        )
        draft = _exclusive_yaml(
            {
                "schema_version": "1.1",
                "foundation": "current",
                "variants": [],
                "guidance": (
                    "site approval 后填写完整 experiment contract；"
                    "首轮 baseline 必须是 7 scaffolds × 40 candidates"
                ),
            },
            root / "strategy-draft.yaml",
        )
    except Exception:
        raise
    return CommandResult(
        status="initialized",
        phase="prepare",
        project_id=initial.project_id,
        artifacts=(descriptor_path, decisions, draft, revision, root / "inputs"),
        next_actions=(
            NextAction(
                command=f"easydesign target prepare {root}",
                description="解析靶点来源并建立可审计 target foundation。",
            ),
        ),
    )


def _descriptor(root: Path) -> ProjectDescriptor:
    path = root / "PROJECT.yaml"
    if not path.is_file():
        if any((root / name).is_file() for name in STAGE_FILENAMES.values()):
            raise ConfigurationError("legacy-stage-project 仅支持 project status/read-only view")
        raise ConfigurationError(f"项目缺少 PROJECT.yaml: {root}")
    return ProjectDescriptor.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))


def _project_id(root: Path) -> str:
    return load_run_config(project_config_path(root), source_base_dir=root).config.project_id


def _runs(root: Path) -> tuple[RunSummary, ...]:
    project_id = _project_id(root)
    values = tuple(
        item
        for item in list_runs(WorkspaceContext.discover().runs_root)
        if item.project_id == project_id
    )
    return tuple(sorted(values, key=lambda item: (item.run_id, item.manifest_revision)))


def _latest_manifest(run_root: Path) -> tuple[RunManifest, Path]:
    path = run_root / "manifests" / read_last_text_line(run_root / "manifests/LATEST")
    return load_model(path, RunManifest), path


def _artifact(run_root: Path, artifact_id: str) -> tuple[ArtifactRef, Path]:
    run, _ = _latest_manifest(run_root)
    for stage_ref in reversed(run.stage_manifest_refs):
        stage = load_model(stage_ref.verify(run_root), StageManifest)
        for item in stage.output_artifacts:
            if item.artifact_id == artifact_id:
                return item, item.verify(run_root)
    raise ConfigurationError(f"run manifest 未声明 artifact: {artifact_id}")


def _stage02_approved(summary: RunSummary) -> bool:
    try:
        _artifact(summary.path, "hotspots")
    except ConfigurationError:
        return False
    return True


def _has_internal_stage(summary: RunSummary, number: int) -> bool:
    run, _ = _latest_manifest(summary.path)
    prefix = f"{number:02d}-"
    return any(
        (reference.producer_stage or "").startswith(prefix) for reference in run.stage_manifest_refs
    )


def _latest_target_run(root: Path) -> RunSummary | None:
    candidates = [item for item in _runs(root) if _has_internal_stage(item, 1)]
    return candidates[-1] if candidates else None


def _latest_foundation(root: Path) -> RunSummary | None:
    candidates = [
        item
        for item in _runs(root)
        if {1, 2}.issubset(completed_steps(item.path)) and _stage02_approved(item)
    ]
    pointer = _read_pointer(root, SITE_POINTER)
    if pointer is not None:
        payload = yaml.safe_load(pointer.read_text(encoding="utf-8"))
        run_id = payload.get("run_id") if isinstance(payload, dict) else None
        candidates = [item for item in candidates if item.run_id == run_id]
    return candidates[-1] if candidates else None


def _semantic_evidence(root: Path) -> tuple[EvidenceItem, ...]:
    values: list[EvidenceItem] = []
    for run in _runs(root):
        completed = completed_steps(run.path)
        if _has_internal_stage(run, 7):
            kind, status = "selection-run", run.status
        elif _has_internal_stage(run, 6):
            kind, status = "production-run", run.status
        elif any(_has_internal_stage(run, number) for number in (3, 4, 5)):
            kind, status = "pilot-run", run.status
        elif 2 in completed:
            kind, status = "site-foundation", "approved" if _stage02_approved(run) else "proposed"
        else:
            kind, status = "target-foundation", run.status
        values.append(
            EvidenceItem(kind=kind, identity=run.run_id, status=status, path=run.latest_manifest)
        )
    for path in sorted((root / "strategies").glob("strategy-r*.yaml")):
        values.append(
            EvidenceItem(kind="strategy-revision", identity=path.stem, status="frozen", path=path)
        )
    for path in sorted(root.glob("promotion-*.yaml")):
        values.append(
            EvidenceItem(kind="promotion", identity=path.stem, status="approved", path=path)
        )
    return tuple(values)


def project_status(project_root: Path) -> CommandResult:
    root = resolve_project_path(project_root, must_exist=True)
    if not (root / "PROJECT.yaml").is_file() and any(
        (root / name).is_file() for name in STAGE_FILENAMES.values()
    ):
        config = load_run_config(project_config_path(root), source_base_dir=root).config
        return CommandResult(
            status="legacy-stage-project",
            phase="prepare",
            project_id=config.project_id,
            evidence=_semantic_evidence(root),
            warnings=("旧七 YAML 项目只读；拒绝原地迁移。请新建 Agent-native 项目。",),
        )
    descriptor = _descriptor(root)
    evidence = _semantic_evidence(root)
    foundation = _latest_foundation(root)
    strategies = sorted((root / "strategies").glob("strategy-r*.yaml"))
    pilot_runs = [item for item in _runs(root) if _has_internal_stage(item, 3)]
    productions = [item for item in _runs(root) if _has_internal_stage(item, 6)]
    selections = [item for item in _runs(root) if _has_internal_stage(item, 7)]
    promotion = _read_pointer(root, PROMOTION_POINTER)
    latest = _runs(root)[-1] if _runs(root) else None
    if selections:
        phase: ResearchPhase = "select"
        status = "completed"
        actions: tuple[NextAction, ...] = ()
    elif productions:
        phase, status = "select", "selection-ready"
        actions = (
            NextAction(
                command=f"easydesign select plan {root} --run {productions[-1].run_id}",
                description="核对最终过滤与 Top 200 计划。",
            ),
        )
    elif promotion is not None:
        phase, status = "scale", "scale-ready"
        selection_id = yaml.safe_load(promotion.read_text(encoding="utf-8"))["selection_id"]
        actions = (
            NextAction(
                command=f"easydesign scale plan {root} --selection {selection_id}",
                description="核对 50,000 候选资源计划。",
            ),
        )
    elif pilot_runs:
        latest_pilot = pilot_runs[-1]
        phase = "pilot"
        if _has_internal_stage(latest_pilot, 5):
            status = "pilot-review-ready"
            actions = (
                NextAction(
                    command=f"easydesign pilot review {root} --run {latest_pilot.run_id}",
                    description="比较过滤结果并讨论下一轮策略或人工 promotion。",
                ),
            )
        else:
            latest_job = LocalStepJobController().latest(descriptor.project_id)
            if (
                latest_job is not None
                and latest_job.run_id == latest_pilot.run_id
                and latest_job.status in ACTIVE_JOB_STATUSES
            ):
                status = "pilot-running"
                command = f"easydesign job status {root} --run {latest_pilot.run_id}"
                description = "读取当前 Pilot 的结构化 job 与 heartbeat 状态。"
            else:
                status = "pilot-resume-ready"
                command = f"easydesign job resume {root} --run {latest_pilot.run_id}"
                description = "从最后一个已验证 manifest 继续到 Pilot 过滤边界。"
            actions = (NextAction(command=command, description=description),)
    elif strategies:
        phase, status = "pilot", "pilot-ready"
        actions = (
            NextAction(
                command=f"easydesign pilot plan {root} --strategy {strategies[-1].stem}",
                description="核对 pilot 预算与 backend。",
            ),
        )
    elif foundation is not None:
        phase, status = "strategize", "strategy-draft-ready"
        actions = (
            NextAction(
                command=f"easydesign strategy draft {root}",
                description="基于批准位点讨论并填写策略。",
            ),
        )
    else:
        target = _latest_target_run(root)
        phase = "prepare"
        if target is None:
            status = "target-not-started"
            actions = (
                NextAction(command=f"easydesign target prepare {root}", description="准备靶点。"),
            )
        elif 1 not in completed_steps(target.path):
            status = "target-approval-required"
            decisions = sorted(root.glob(f"target-decision.{target.run_id}.yaml"))
            actions = tuple(
                NextAction(
                    command=f"easydesign target approve {root} --input {decision}",
                    description="审核靶点结构/链歧义后继续。",
                    approval_required=True,
                )
                for decision in decisions
            )
        else:
            status = "site-required"
            actions = (
                NextAction(
                    command=f"easydesign site scan {root} --method both",
                    description="独立运行 SASA 与 ScanNet 候选。",
                ),
                NextAction(
                    command=f"easydesign site propose {root} --input SITE.yaml",
                    description="映射合作者提供的文字 residue 位点。",
                ),
            )
    return CommandResult(
        status=status,
        phase=phase,
        project_id=descriptor.project_id,
        run_id=None if latest is None else latest.run_id,
        manifest=None if latest is None else latest.latest_manifest,
        evidence=evidence,
        next_actions=actions,
    )


def _config_from_base(
    base: EasyDesignRunConfig,
    *,
    stop_after: int,
    stages: dict[int, BaseModel],
) -> EasyDesignRunConfig:
    payload = base.model_dump(mode="python", exclude_none=False)
    payload["workflow"]["execution_mode"] = "review-gated"
    payload["workflow"]["stop_after_stage"] = stop_after
    for number in range(2, 8):
        payload[f"stage{number:02d}"] = (
            stages[number].model_dump(mode="python", exclude_none=False)
            if number in stages
            else None
        )
    return EasyDesignRunConfig.model_validate(payload)


def _launch(
    root: Path,
    *,
    phase: ResearchPhase,
    config: EasyDesignRunConfig,
    internal_start: int,
    base: RunSummary | None,
    run_id: str | None,
    detach: bool,
    actions: tuple[NextAction, ...] = (),
) -> tuple[CommandResult, LocalStepJob]:
    revision = publish_config_revision(root, config)
    controller = LocalStepJobController()
    job = controller.launch(
        operation="run",
        project_id=config.project_id,
        project_root=root,
        step=internal_start,
        config_path=revision,
        run_id=run_id,
        run_root=None if base is None else base.path,
    )
    observed = wait_or_detach(controller, job, detach=detach)
    result = CommandResult(
        status=observed.status,
        phase=phase,
        project_id=config.project_id,
        run_id=observed.run_id or run_id,
        job_id=observed.job_id,
        manifest=observed.run_manifest,
        artifacts=(revision,),
        next_actions=actions,
    )
    return result, observed


def target_prepare(project_root: Path, *, detach: bool = False) -> CommandResult:
    root = resolve_project_path(project_root, must_exist=True)
    _descriptor(root)
    existing = _latest_target_run(root)
    if existing is not None:
        return CommandResult(
            status="no-op",
            phase="prepare",
            project_id=_project_id(root),
            run_id=existing.run_id,
            manifest=existing.latest_manifest,
            next_actions=(
                NextAction(
                    command=f"easydesign site scan {root} --method both",
                    description="准备位点候选。",
                ),
            ),
        )
    config = load_run_config(project_config_path(root), source_base_dir=root).config
    result, observed = _launch(
        root,
        phase="prepare",
        config=config,
        internal_start=1,
        base=None,
        run_id=None,
        detach=detach,
    )
    artifacts = list(result.artifacts)
    actions: list[NextAction] = []
    if observed.status == "awaiting-human-approval" and observed.run_root is not None:
        decision = root / f"target-decision.{observed.run_id}.yaml"
        export_decision(observed.run_root, output=decision)
        artifacts.append(decision)
        actions.append(
            NextAction(
                command=f"easydesign target approve {root} --input {decision}",
                description="审核结构/链歧义后继续 target prepare。",
                approval_required=True,
            )
        )
    elif observed.status == "succeeded":
        actions.extend(
            (
                NextAction(
                    command=f"easydesign view {root} --run {observed.run_id}",
                    description="只读检查靶点结构。",
                ),
                NextAction(
                    command=f"easydesign site scan {root} --method both",
                    description="独立生成 SASA/ScanNet 位点候选。",
                ),
            )
        )
    return result.model_copy(update={"artifacts": tuple(artifacts), "next_actions": tuple(actions)})


def target_approve(project_root: Path, *, input_path: Path, detach: bool = False) -> CommandResult:
    root = resolve_project_path(project_root, must_exist=True)
    target = _latest_target_run(root)
    if target is None:
        raise ConfigurationError("项目没有可批准的 target run")
    record = approve_decision(target.path, input_path=input_path.expanduser().resolve(strict=True))
    controller = LocalStepJobController()
    job = controller.launch(
        operation="decision",
        project_id=target.project_id,
        project_root=root,
        step=1,
        decision_record=record,
        run_id=target.run_id,
        run_root=target.path,
    )
    observed = wait_or_detach(controller, job, detach=detach)
    return CommandResult(
        status=observed.status,
        phase="prepare",
        project_id=target.project_id,
        run_id=observed.run_id,
        job_id=observed.job_id,
        manifest=observed.run_manifest,
        artifacts=(record,),
        next_actions=(
            NextAction(
                command=f"easydesign site scan {root} --method both", description="准备位点候选。"
            ),
        ),
    )


def _site_fragment_from_file(path: Path) -> Stage02Config:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ConfigurationError("SITE YAML 顶层必须是 mapping")
    if "mode" in payload:
        fragment = Stage02Config.model_validate(payload)
        embedded_approval = (
            fragment.user_regions is not None and fragment.user_regions.approval is not None
        )
        if embedded_approval or fragment.unattended_approval is not None:
            raise ConfigurationError(
                "site propose 不接受内嵌 approval；必须使用 site approve --confirm"
            )
        return fragment
    regions = payload.get("regions")
    if not isinstance(regions, list) or not regions:
        raise ConfigurationError("SITE YAML 必须提供非空 regions")
    return Stage02Config.model_validate(
        {
            "mode": "user-provided",
            "methods": [],
            "automatic": None,
            "annotations": {"uniprot": "if_available"},
            "user_regions": {
                "source": {
                    "type": "residue-list",
                    "numbering": payload.get("numbering", "label"),
                    "regions": regions,
                }
            },
        }
    )


def _site_config(root: Path, fragment: Stage02Config, base: RunSummary) -> EasyDesignRunConfig:
    resolved, _ = load_resolved_run_config(base.path)
    return _config_from_base(resolved.user_config, stop_after=2, stages={2: fragment})


def _new_run_id(prefix: str) -> str:
    return f"{prefix}-{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}-{uuid4().hex[:8]}"


def _export_site_proposals(root: Path, run_root: Path) -> tuple[Path, ...]:
    run, _ = _latest_manifest(run_root)
    stage_ref = next(
        (item for item in run.stage_manifest_refs if item.producer_stage == "02-hotspot-discovery"),
        None,
    )
    if stage_ref is None:
        return ()
    stage = load_model(stage_ref.verify(run_root), StageManifest)
    ids = {item.artifact_id for item in stage.output_artifacts}
    options: tuple[tuple[str, RegionMethod | None, str], ...] = (
        ("sasa", RegionMethod.SASA_SURFACE_DIVERSITY, "sasa-recommended-regions"),
        ("scannet", RegionMethod.SCANNET_EPITOPE_NO_MSA, "scannet-recommended-regions"),
        ("manual", None, "user-provided-regions"),
    )
    outputs: list[Path] = []
    for label, method, artifact_id in options:
        if artifact_id not in ids:
            continue
        output = root / f"site-proposal.{label}.{run.run_id}.yaml"
        if not output.exists():
            export_hotspot_review(run_root, method=method, output=output)
        outputs.append(output)
    return tuple(outputs)


def _run_site(root: Path, fragment: Stage02Config, *, detach: bool) -> CommandResult:
    target = _latest_target_run(root)
    if target is None:
        raise ConfigurationError("必须先完成 target prepare")
    run_id = _new_run_id("foundation")
    result, observed = _launch(
        root,
        phase="prepare",
        config=_site_config(root, fragment, target),
        internal_start=2,
        base=target,
        run_id=run_id,
        detach=detach,
    )
    proposals: tuple[Path, ...] = ()
    if observed.status != "detached" and observed.run_root is not None:
        proposals = _export_site_proposals(root, observed.run_root)
    actions = tuple(
        NextAction(
            command=f"easydesign site approve {root} --input {path} --confirm",
            description=f"在 Viewer 核对 {path.name} 后批准。",
            approval_required=True,
        )
        for path in proposals
    )
    return result.model_copy(
        update={
            "artifacts": (*result.artifacts, *proposals),
            "next_actions": (
                NextAction(
                    command=f"easydesign view {root} --run {observed.run_id}",
                    description="只读查看 A/B/C 区域；红/蓝/黄。",
                ),
                *actions,
            ),
        }
    )


def site_scan(
    project_root: Path, *, method: Literal["sasa", "scannet", "both"], detach: bool = False
) -> CommandResult:
    root = resolve_project_path(project_root, must_exist=True)
    methods = ["sasa", "scannet"] if method == "both" else [method]
    fragment = Stage02Config.model_validate(
        {
            "mode": "automatic",
            "methods": methods,
            "automatic": {},
            "annotations": {"uniprot": "if_available"},
            "user_regions": None,
        }
    )
    return _run_site(root, fragment, detach=detach)


def site_propose(
    project_root: Path, *, input_path: Path | None, from_pse_colors: bool, detach: bool = False
) -> CommandResult:
    root = resolve_project_path(project_root, must_exist=True)
    if from_pse_colors:
        fragment = Stage02Config.model_validate(
            {
                "mode": "detect",
                "methods": ["sasa", "scannet"],
                "automatic": {},
                "annotations": {"uniprot": "if_available"},
                "user_regions": {"source": {"type": "pse-colors"}},
            }
        )
    else:
        if input_path is None:
            raise ConfigurationError("site propose 必须提供 --input 或 --from-pse-colors")
        fragment = _site_fragment_from_file(input_path.expanduser().resolve(strict=True))
    return _run_site(root, fragment, detach=detach)


def site_approve(project_root: Path, *, input_path: Path, confirm: bool) -> CommandResult:
    root = resolve_project_path(project_root, must_exist=True)
    selected = input_path.expanduser().resolve(strict=True)
    if not selected.is_relative_to(root):
        raise ConfigurationError("site proposal 必须位于当前项目")
    if not confirm:
        return CommandResult(
            status="confirmation-required",
            phase="prepare",
            project_id=_project_id(root),
            artifacts=(selected,),
            next_actions=(
                NextAction(
                    command=f"easydesign site approve {root} --input {selected} --confirm",
                    description="发布新的不可变 target/site foundation。",
                    approval_required=True,
                ),
            ),
        )
    runs = [item for item in _runs(root) if item.run_id in selected.name]
    if len(runs) != 1:
        raise ConfigurationError("site proposal 文件名无法唯一解析来源 run")
    summary = runs[0]
    hotspots = approve_hotspots(summary.path, input_path=selected)
    bind_project_run(root, summary.path)
    _, manifest = _latest_manifest(summary.path)
    number = len(tuple(root.glob("site-approved.r*.yaml"))) + 1
    receipt_path = root / f"site-approved.r{number:06d}.yaml"
    receipt = {
        "schema_version": "1.0",
        "foundation_id": f"foundation-r{number:06d}",
        "run_id": summary.run_id,
        "proposal": selected.relative_to(root).as_posix(),
        "proposal_sha256": sha256_file(selected),
        "hotspots": hotspots.relative_to(summary.path).as_posix(),
        "hotspots_sha256": sha256_file(hotspots),
        "manifest": manifest.relative_to(summary.path).as_posix(),
        "manifest_sha256": sha256_file(manifest),
        "approved_at": datetime.now(UTC).isoformat(),
    }
    _exclusive_yaml(receipt, receipt_path)
    _append_pointer(root, SITE_POINTER, receipt_path.relative_to(root))
    return CommandResult(
        status="target-and-site-ready",
        phase="strategize",
        project_id=summary.project_id,
        run_id=summary.run_id,
        manifest=manifest,
        artifacts=(hotspots, receipt_path, root / SITE_POINTER),
        next_actions=(
            NextAction(
                command=f"easydesign strategy draft {root}",
                description="讨论 target crop、binding subset、scaffold 与 CDR 参数。",
            ),
        ),
    )


def _load_hotspots(summary: RunSummary) -> HotspotsFile:
    _, path = _artifact(summary.path, "hotspots")
    return HotspotsFile.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))


def _target_length(summary: RunSummary) -> int:
    _, path = _artifact(summary.path, "target-bundle")
    payload = json.loads(path.read_text(encoding="utf-8"))
    length = payload.get("sequence_length")
    if not isinstance(length, int) or length < 1:
        raise ConfigurationError("Target Bundle 缺少有效 sequence_length")
    return length


def _validate_first_pilot_strategy(strategy: ResearchStrategy) -> None:
    """Enforce the VHH7 coverage product invariant before any first pilot."""

    if (
        len(SCAFFOLD_IDS) != FIRST_PILOT_SCAFFOLD_COUNT
        or len(set(SCAFFOLD_IDS)) != FIRST_PILOT_SCAFFOLD_COUNT
    ):
        raise ConfigurationError("official-vhh7-v1 registry 必须精确包含 7 个唯一 scaffold")
    wrong_counts = [
        item.id for item in strategy.variants if item.candidates != FIRST_PILOT_CANDIDATES_PER_GROUP
    ]
    if wrong_counts:
        raise ConfigurationError(
            f"首轮每个 experiment group 必须生成 40 candidates: {wrong_counts}"
        )
    baseline = tuple(
        item
        for item in strategy.variants
        if item.native_boltzgen_yaml is None
        and (strategy.schema_version == "1.0" or item.role == "baseline")
    )
    covered = {scaffold for item in baseline for scaffold in item.scaffold_ids}
    missing = sorted(set(SCAFFOLD_IDS) - covered)
    if missing:
        raise ConfigurationError(
            f"首轮 baseline 不得预筛 scaffold；缺少 official-vhh7-v1 scaffold: {missing}"
        )
    required = FIRST_PILOT_SCAFFOLD_COUNT * FIRST_PILOT_CANDIDATES_PER_GROUP
    baseline_candidates = sum(item.candidates * len(item.scaffold_ids) for item in baseline)
    if baseline_candidates < required:
        raise ConfigurationError(f"首轮 baseline 至少需要 7 scaffolds × 40 = {required} candidates")


def load_strategy(project_root: Path, path: Path) -> ResearchStrategy:
    root = resolve_project_path(project_root, must_exist=True)
    selected = path if path.is_absolute() else root / path
    selected = selected.resolve(strict=True)
    if not selected.is_relative_to(root):
        raise ConfigurationError("strategy 文件必须位于当前项目")
    payload = yaml.safe_load(selected.read_text(encoding="utf-8"))
    strategy = ResearchStrategy.model_validate(payload)
    foundation = _latest_foundation(root)
    if foundation is None:
        raise ConfigurationError("strategy 需要当前 approved target/site foundation")
    hotspots = _load_hotspots(foundation)
    approved = {item.id: set(item.label_seq_ids) for item in hotspots.hotspot_sets}
    all_approved = set().union(*approved.values())
    target_length = _target_length(foundation)
    if not any(_has_internal_stage(item, 5) for item in _runs(root)):
        _validate_first_pilot_strategy(strategy)
    for variant in strategy.variants:
        if variant.native_boltzgen_yaml is not None:
            native = variant.native_boltzgen_yaml
            native = native if native.is_absolute() else root / native
            native = native.resolve(strict=True)
            if not native.is_relative_to(root) or not native.is_file():
                raise ConfigurationError("native BoltzGen YAML 必须复制到当前项目")
            if variant.native_boltzgen_sha256 != sha256_file(native):
                raise ConfigurationError("native BoltzGen YAML SHA-256 不匹配")
            continue
        if variant.hotspot_set_id is not None and variant.hotspot_set_id not in approved:
            raise ConfigurationError(f"未知 approved hotspot set: {variant.hotspot_set_id}")
        selected_residues = set(variant.binding_label_seq_ids or ())
        if selected_residues and not selected_residues.issubset(all_approved):
            raise ConfigurationError("binding subset 包含未批准 residue")
        if variant.target_crop is not None:
            if variant.target_crop.end > target_length:
                raise ConfigurationError("target crop 超出 Target Bundle sequence_length")
            residues = selected_residues or approved.get(variant.hotspot_set_id or "", set())
            if any(
                item < variant.target_crop.start or item > variant.target_crop.end
                for item in residues
            ):
                raise ConfigurationError("target crop 未覆盖全部选择的 binding residues")
    return strategy


def strategy_draft(
    project_root: Path, *, source: str | None = None, from_pilot: str | None = None
) -> CommandResult:
    root = resolve_project_path(project_root, must_exist=True)
    if _latest_foundation(root) is None:
        raise ConfigurationError("必须先批准 target/site foundation")
    draft = root / "strategy-draft.yaml"
    if source is not None:
        candidates = [
            path
            for path in (root / "strategies").glob("strategy-r*.yaml")
            if source in {path.stem, path.name}
        ]
        if len(candidates) != 1:
            raise ConfigurationError("--from 无法唯一解析 strategy revision")
        payload = yaml.safe_load(candidates[0].read_text(encoding="utf-8"))
    elif from_pilot is not None:
        pilot = next(
            (
                item
                for item in _runs(root)
                if item.run_id == from_pilot and _has_internal_stage(item, 5)
            ),
            None,
        )
        if pilot is None:
            raise ConfigurationError("--from-pilot 必须引用已完成 pilot")
        resolved, _ = load_resolved_run_config(pilot.path)
        source_revision = resolved.user_config.stage03
        payload = {
            "schema_version": "1.1",
            "foundation": "current",
            "variants": [],
            "previous_stage03": source_revision.model_dump(mode="json")
            if source_revision
            else None,
            "guidance": f"根据 pilot {from_pilot} review 结果填写新 variants",
        }
    else:
        foundation = _latest_foundation(root)
        assert foundation is not None
        hotspot_sets = [item.id for item in _load_hotspots(foundation).hotspot_sets]
        payload = {
            "schema_version": "1.1",
            "foundation": "current",
            "variants": [
                {
                    "id": "baseline",
                    "hypothesis_id": "h-baseline-all-scaffolds",
                    "role": "baseline",
                    "evidence_refs": [
                        f"run:{foundation.run_id}",
                        "scaffold-registry:official-vhh7-v1",
                    ],
                    "changed_factors": ["scaffold_id"],
                    "held_constant": [
                        "target_state",
                        "target_context",
                        "approved_site",
                        "hotspot_set",
                        "target_crop",
                        "cdr_design",
                        "candidates_per_strategy",
                    ],
                    "hotspot_set_id": hotspot_sets[0],
                    "binding_label_seq_ids": None,
                    "scaffold_ids": list(SCAFFOLD_IDS),
                    "target_crop": None,
                    "cdr_overrides": [],
                    "candidates": FIRST_PILOT_CANDIDATES_PER_GROUP,
                    "native_boltzgen_yaml": None,
                    "native_boltzgen_sha256": None,
                    "rationale": (
                        "首轮不预筛 scaffold；在相同 site/crop/CDR 下测量 scaffold effect。"
                    ),
                    "expected_result": (
                        "7 个 scaffold 各生成 40 个、合计 280 个 baseline candidates，"
                        "用于 hard-gate 过滤与 scaffold 对照。"
                    ),
                    "failure_interpretation": (
                        "单个 scaffold 失败只支持 scaffold-specific incompatibility；"
                        "全部失败才优先检查共同 site/context 或生成约束。"
                    ),
                }
            ],
        }
    _replace_yaml(payload, draft)
    return CommandResult(
        status="draft-ready",
        phase="strategize",
        project_id=_project_id(root),
        artifacts=(draft,),
        next_actions=(
            NextAction(
                command=f"easydesign strategy validate {root} --config {draft}",
                description="在 staging 编译并校验，不发布 revision。",
            ),
        ),
    )


def _compiled_strategy_variants(
    root: Path,
    strategy: ResearchStrategy,
) -> tuple[tuple[ExplicitStrategyVariant, ...], tuple[NativeStrategyVariant, ...]]:
    explicit = tuple(
        ExplicitStrategyVariant(
            variant_id=item.id,
            hotspot_set_id=item.hotspot_set_id,
            binding_label_seq_ids=item.binding_label_seq_ids,
            scaffold_ids=item.scaffold_ids,
            target_crop=(
                None
                if item.target_crop is None
                else CompiledTargetCrop(
                    start=item.target_crop.start,
                    end=item.target_crop.end,
                )
            ),
            cdr_overrides=tuple(
                CompiledCdrOverride(
                    cdr=override.cdr,
                    design_res_index=override.design_res_index,
                    insertion_num_residues=override.insertion_num_residues,
                )
                for override in item.cdr_overrides
            ),
            candidates_per_strategy=item.candidates,
            hypothesis_id=item.hypothesis_id,
            role=item.role,
            evidence_refs=item.evidence_refs,
            changed_factors=item.changed_factors,
            held_constant=item.held_constant,
            rationale=item.rationale,
            expected_result=item.expected_result,
            failure_interpretation=item.failure_interpretation,
        )
        for item in strategy.variants
        if item.native_boltzgen_yaml is None
    )
    native = tuple(
        NativeStrategyVariant(
            variant_id=item.id,
            scaffold_id=item.scaffold_ids[0],
            yaml_text=(
                (
                    item.native_boltzgen_yaml
                    if item.native_boltzgen_yaml.is_absolute()
                    else root / item.native_boltzgen_yaml
                )
                .resolve(strict=True)
                .read_text(encoding="utf-8")
            ),
            source_sha256=cast(str, item.native_boltzgen_sha256),
            candidates_per_strategy=item.candidates,
            hypothesis_id=item.hypothesis_id,
            role=item.role,
            evidence_refs=item.evidence_refs,
            changed_factors=item.changed_factors,
            held_constant=item.held_constant,
            rationale=item.rationale,
            expected_result=item.expected_result,
            failure_interpretation=item.failure_interpretation,
        )
        for item in strategy.variants
        if item.native_boltzgen_yaml is not None
    )
    return explicit, native


def strategy_validate(project_root: Path, *, config_path: Path) -> CommandResult:
    root = resolve_project_path(project_root, must_exist=True)
    strategy = load_strategy(root, config_path)
    selected_config = (config_path if config_path.is_absolute() else root / config_path).resolve()
    total = sum(
        item.candidates * len(item.scaffold_ids)
        for item in strategy.variants
        if item.native_boltzgen_yaml is None
    ) + sum(item.candidates for item in strategy.variants if item.native_boltzgen_yaml is not None)
    foundation = _latest_foundation(root)
    assert foundation is not None
    _, target_cif = _artifact(foundation.path, "target-structure")
    hotspots = _load_hotspots(foundation)
    explicit, native = _compiled_strategy_variants(root, strategy)
    context = WorkspaceContext.discover()
    staging = context.runtime_root / "tmp" / f"strategy-validate-{uuid4().hex}"
    context.require_write_path(staging, purpose="strategy staging validation")
    profile = load_runtime_profile(None).profile
    runtime = profile.backends.boltzgen_validation or profile.backends.boltzgen
    if runtime is None:
        raise ConfigurationError("runtime profile 未配置 boltzgen-validation backend")
    adapter = BoltzGenCheckAdapter(
        executable=runtime.executable,
        repository_root=runtime.repository_root,
        cache_root=runtime.cache_root,
        timeout_seconds=runtime.timeout_seconds,
        validation_workers=runtime.validation_workers,
        offline_mode=runtime.offline_mode,
        require_generation_assets=False,
    )
    try:
        capability = adapter.probe()
        _, compiled = compile_vhh_strategy_plan(
            target_cif=target_cif,
            hotspots=hotspots,
            artifacts_root=staging,
            variants=explicit,
            native_variants=native,
        )
        report = adapter.validate(
            artifacts_root=staging,
            strategies=compiled,
            logs_root=staging / "validation-logs",
            checked_at=datetime.now(UTC),
        )
        if report.status != "passed":
            failed = [item.strategy_id for item in report.items if item.status == "failed"]
            raise ConfigurationError(f"BoltzGen staging check 失败: {failed}")
    finally:
        if staging.is_dir():
            shutil.rmtree(staging)
    return CommandResult(
        status="valid",
        phase="strategize",
        project_id=_project_id(root),
        artifacts=(selected_config,),
        evidence=(
            EvidenceItem(
                kind="strategy-validation",
                identity=sha256_file(selected_config),
                status="backend-passed",
                metadata={
                    "variant_count": len(strategy.variants),
                    "planned_candidates": total,
                    "compiled_strategy_count": len(compiled),
                    "boltzgen_version": capability["version"],
                    "boltzgen_commit": capability["commit"],
                },
            ),
        ),
        next_actions=(
            NextAction(
                command=(f"easydesign strategy freeze {root} --config {selected_config} --confirm"),
                description="批准并冻结不可变策略 revision。",
                approval_required=True,
            ),
        ),
        warnings=("pilot 的不可变 attempt 会再次执行同一 BoltzGen check。",),
    )


def strategy_freeze(project_root: Path, *, config_path: Path, confirm: bool) -> CommandResult:
    root = resolve_project_path(project_root, must_exist=True)
    strategy = load_strategy(root, config_path)
    selected = (config_path if config_path.is_absolute() else root / config_path).resolve(
        strict=True
    )
    if not confirm:
        return CommandResult(
            status="confirmation-required",
            phase="strategize",
            project_id=_project_id(root),
            artifacts=(selected,),
            next_actions=(
                NextAction(
                    command=f"easydesign strategy freeze {root} --config {selected} --confirm",
                    description="冻结后不可覆盖。",
                    approval_required=True,
                ),
            ),
        )
    validation = strategy_validate(root, config_path=selected)
    number = len(tuple((root / "strategies").glob("strategy-r*.yaml"))) + 1
    destination = root / "strategies" / f"strategy-r{number:06d}.yaml"
    _exclusive_yaml(strategy, destination)
    _append_pointer(root, STRATEGY_POINTER, destination.relative_to(root))
    return CommandResult(
        status="strategy-frozen",
        phase="pilot",
        project_id=_project_id(root),
        artifacts=(destination, root / STRATEGY_POINTER),
        evidence=validation.evidence,
        next_actions=(
            NextAction(
                command=f"easydesign pilot plan {root} --strategy {destination.stem}",
                description="核对 pilot 预算与资源。",
            ),
        ),
    )


def _strategy_revision(root: Path, value: str) -> Path:
    candidates = [
        path
        for path in (root / "strategies").glob("strategy-r*.yaml")
        if value in {path.stem, path.name}
    ]
    if len(candidates) != 1:
        raise ConfigurationError("strategy revision 无法唯一解析")
    load_strategy(root, candidates[0])
    return candidates[0]


def _resource_evidence(kind: str, count: int, *, strategies: int) -> EvidenceItem:
    context = WorkspaceContext.discover()
    disk = shutil.disk_usage(context.root)
    try:
        gpus = [item.model_dump(mode="json") for item in NvidiaSmiProbe().snapshots()]
    except Exception as error:
        gpus = [{"probe_error": f"{type(error).__name__}: {error}"}]
    return EvidenceItem(
        kind="resource-plan",
        identity=kind,
        status="planned",
        metadata={
            "candidate_count": count,
            "strategy_count": strategies,
            "gpu": gpus,
            "disk_free_gib": round(disk.free / 1024**3, 2),
            "disk_safety_margin_gib": 10,
            "backend": "boltzgen-0.3.2",
        },
    )


def pilot_plan(project_root: Path, *, strategy_revision: str) -> CommandResult:
    root = resolve_project_path(project_root, must_exist=True)
    path = _strategy_revision(root, strategy_revision)
    strategy = load_strategy(root, path)
    count = sum(item.candidates * max(1, len(item.scaffold_ids)) for item in strategy.variants)
    return CommandResult(
        status="confirmation-required",
        phase="pilot",
        project_id=_project_id(root),
        artifacts=(path,),
        evidence=(_resource_evidence("pilot", count, strategies=len(strategy.variants)),),
        next_actions=(
            NextAction(
                command=f"easydesign pilot run {root} --strategy {path.stem} --confirm",
                description="创建独立 pilot run，执行策略编译、生成、标准过滤和诊断。",
                approval_required=True,
            ),
        ),
    )


def _pilot_config(root: Path, foundation: RunSummary, strategy_path: Path) -> EasyDesignRunConfig:
    strategy = load_strategy(root, strategy_path)
    candidates = max(item.candidates for item in strategy.variants)
    resolved, _ = load_resolved_run_config(foundation.path)
    explicit, native = _compiled_strategy_variants(root, strategy)
    stage03 = Stage03Config(
        scaffold_ids=None,
        candidates_per_strategy=candidates,
        variants=explicit,
        native_variants=native,
    )
    stage02 = resolved.user_config.stage02
    if stage02 is None:
        raise ConfigurationError("approved foundation 缺少 frozen site config")
    return _config_from_base(
        resolved.user_config,
        stop_after=5,
        stages={
            2: stage02,
            3: stage03,
            4: Stage04Config(required_complete_candidates_per_strategy=candidates),
            5: Stage05Config(),
        },
    )


def pilot_run(
    project_root: Path, *, strategy_revision: str, confirm: bool, detach: bool = False
) -> CommandResult:
    root = resolve_project_path(project_root, must_exist=True)
    path = _strategy_revision(root, strategy_revision)
    if not confirm:
        return pilot_plan(root, strategy_revision=strategy_revision)
    foundation = _latest_foundation(root)
    if foundation is None:
        raise ConfigurationError("pilot 需要 approved foundation")
    run_id = _new_run_id("pilot")
    result, _ = _launch(
        root,
        phase="pilot",
        config=_pilot_config(root, foundation, path),
        internal_start=3,
        base=foundation,
        run_id=run_id,
        detach=detach,
    )
    return result.model_copy(
        update={
            "artifacts": (*result.artifacts, path),
            "next_actions": (
                NextAction(
                    command=f"easydesign pilot review {root} --run {run_id}",
                    description="查看结构化通过率、失败规则和代表候选。",
                ),
            ),
        }
    )


def _run_by_id(root: Path, run_id: str) -> RunSummary:
    values = [item for item in _runs(root) if item.run_id == run_id]
    if len(values) != 1:
        raise ConfigurationError(f"run 无法唯一解析: {run_id}")
    return values[0]


def pilot_review(project_root: Path, *, run_id: str) -> CommandResult:
    root = resolve_project_path(project_root, must_exist=True)
    run = _run_by_id(root, run_id)
    if not _has_internal_stage(run, 5):
        raise ConfigurationError("pilot review 只接受完成内部过滤阶段的 run")
    evidence: list[EvidenceItem] = [
        EvidenceItem(
            kind="pilot-run", identity=run.run_id, status=run.status, path=run.latest_manifest
        )
    ]
    promotable_strategy_ids: tuple[str, ...] = ()
    experiment_groups: dict[str, dict[str, Any]] = {}
    try:
        _, strategy_bundle_path = _artifact(run.path, "strategy-bundle")
        strategy_bundle = json.loads(strategy_bundle_path.read_text(encoding="utf-8"))
    except ConfigurationError:
        strategy_bundle = {"strategies": []}
    for item in strategy_bundle.get("strategies", []):
        if not isinstance(item, dict) or not isinstance(item.get("strategy_id"), str):
            continue
        experiment_groups[item["strategy_id"]] = {
            key: item.get(key)
            for key in (
                "hypothesis_id",
                "role",
                "evidence_refs",
                "changed_factors",
                "held_constant",
                "rationale",
                "expected_result",
                "failure_interpretation",
                "candidates_per_strategy",
            )
        }
    for artifact_id in (
        "stage05-summary",
        "pilot-filter-report",
        "promotion-candidates",
        "filter-report",
    ):
        try:
            ref, path = _artifact(run.path, artifact_id)
        except ConfigurationError:
            continue
        metadata: dict[str, Any] = {"sha256": ref.sha256}
        if artifact_id == "pilot-filter-report":
            report = json.loads(path.read_text(encoding="utf-8"))
            try:
                _, candidate_index_path = _artifact(run.path, "candidate-index")
                candidate_index = json.loads(candidate_index_path.read_text(encoding="utf-8"))
            except ConfigurationError:
                candidate_index = {"candidates": []}
            candidates_by_id = {
                item.get("candidate_id"): item
                for item in candidate_index.get("candidates", [])
                if isinstance(item, dict)
            }
            failure_counts: dict[str, int] = {}
            representatives: dict[str, dict[str, Any]] = {}
            for candidate in report.get("candidate_records", []):
                for decision in candidate.get("hard_gate_decisions", []):
                    if not decision.get("passed", False):
                        rule_id = str(decision.get("rule_id", "unknown"))
                        failure_counts[rule_id] = failure_counts.get(rule_id, 0) + 1
                strategy_id = str(candidate.get("strategy_id", "unknown"))
                existing = representatives.get(strategy_id)
                if existing is None or (
                    candidate.get("eligible_unique_pass")
                    and not existing.get("eligible_unique_pass")
                ):
                    indexed = candidates_by_id.get(candidate.get("candidate_id"), {})
                    representatives[strategy_id] = {
                        "candidate_id": candidate.get("candidate_id"),
                        "eligible_unique_pass": candidate.get("eligible_unique_pass"),
                        "original_structure": (
                            indexed.get("original_structure", {}).get("relative_path")
                        ),
                        "refolded_structure": (
                            indexed.get("refolded_structure", {}).get("relative_path")
                        ),
                    }
            promoted = report.get(
                "promoted_strategy_ids",
                report.get("selected_strategy_ids", []),
            )
            promotable_strategy_ids = tuple(str(item) for item in promoted)
            metadata.update(
                {
                    "report_status": report.get("status"),
                    "strategy_summaries": report.get("strategy_summaries", []),
                    "failure_rule_counts": dict(sorted(failure_counts.items())),
                    "representative_candidates": representatives,
                    "promoted_strategy_ids": list(promotable_strategy_ids),
                    "experiment_groups": experiment_groups,
                }
            )
        evidence.append(
            EvidenceItem(
                kind="pilot-review-artifact",
                identity=artifact_id,
                status="checksum-verified",
                path=path,
                metadata=metadata,
            )
        )
    actions: tuple[NextAction, ...] = (
        NextAction(
            command=f"easydesign strategy draft {root} --from-pilot {run_id}",
            description="根据负结果或诊断创建下一版策略。",
        ),
    )
    if promotable_strategy_ids:
        actions = (
            *actions,
            NextAction(
                command=(
                    f"easydesign pilot promote {root} --run {run_id} "
                    f"--strategy {','.join(promotable_strategy_ids)} --confirm"
                ),
                description="由研究者从合法 Tier A 策略中选择进入 scale 的集合。",
                approval_required=True,
            ),
        )
    return CommandResult(
        status="review-ready",
        phase="pilot",
        project_id=run.project_id,
        run_id=run.run_id,
        manifest=run.latest_manifest,
        evidence=tuple(evidence),
        next_actions=actions,
    )


def pilot_promote(
    project_root: Path, *, run_id: str, strategy_ids: tuple[str, ...], confirm: bool
) -> CommandResult:
    root = resolve_project_path(project_root, must_exist=True)
    run = _run_by_id(root, run_id)
    if not _has_internal_stage(run, 5):
        raise ConfigurationError("只能从完成 pilot 过滤的 run promotion")
    _, report_path = _artifact(run.path, "pilot-filter-report")
    report = json.loads(report_path.read_text(encoding="utf-8"))
    if report.get("status") == "stopped-no-tier-a":
        raise ConfigurationError("科学负结果没有合法 promotion 候选；请创建新策略 revision")
    eligible = set(report.get("promoted_strategy_ids", report.get("selected_strategy_ids", [])))
    if not set(strategy_ids).issubset(eligible):
        raise ConfigurationError("promotion 只能选择 Stage 05 合法 Tier A strategy")
    _, bundle_path = _artifact(run.path, "strategy-bundle")
    bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    known = {item["strategy_id"] for item in bundle.get("strategies", [])}
    if not strategy_ids or not set(strategy_ids).issubset(known):
        raise ConfigurationError("promotion strategy 必须来自 checksum-verified StrategyBundle")
    if not confirm:
        return CommandResult(
            status="confirmation-required",
            phase="pilot",
            project_id=run.project_id,
            run_id=run.run_id,
            manifest=run.latest_manifest,
            next_actions=(
                NextAction(
                    command=(
                        f"easydesign pilot promote {root} --run {run_id} "
                        f"--strategy {','.join(strategy_ids)} --confirm"
                    ),
                    description="发布人工 promotion receipt。",
                    approval_required=True,
                ),
            ),
        )
    selection_id = f"selection-{uuid4().hex[:12]}"
    receipt = PromotionReceipt(
        selection_id=selection_id,
        project_id=run.project_id,
        pilot_run_id=run.run_id,
        pilot_manifest_sha256=sha256_file(run.latest_manifest),
        strategy_ids=strategy_ids,
        approved_at=datetime.now(UTC),
    )
    path = _exclusive_yaml(receipt, root / f"promotion-{selection_id}.yaml")
    _append_pointer(root, PROMOTION_POINTER, path.relative_to(root))
    return CommandResult(
        status="promoted",
        phase="scale",
        project_id=run.project_id,
        run_id=run.run_id,
        manifest=run.latest_manifest,
        artifacts=(path, root / PROMOTION_POINTER),
        next_actions=(
            NextAction(
                command=f"easydesign scale plan {root} --selection {selection_id}",
                description="核对生产资源和 50,000 候选分配。",
            ),
        ),
    )


def _promotion(root: Path, selection: str) -> tuple[PromotionReceipt, Path]:
    values = [
        path
        for path in root.glob("promotion-*.yaml")
        if selection in {path.stem.removeprefix("promotion-"), path.name, path.stem}
    ]
    if len(values) != 1:
        raise ConfigurationError("selection 无法唯一解析")
    receipt = PromotionReceipt.model_validate(yaml.safe_load(values[0].read_text(encoding="utf-8")))
    if receipt.project_id != _descriptor(root).project_id:
        raise ConfigurationError("selection 不属于当前 project")
    pilot = _run_by_id(root, receipt.pilot_run_id)
    if sha256_file(pilot.latest_manifest) != receipt.pilot_manifest_sha256:
        raise ConfigurationError("selection 引用的 pilot manifest identity 已变化")
    return receipt, values[0]


def scale_plan(project_root: Path, *, selection: str, count: int = 50_000) -> CommandResult:
    root = resolve_project_path(project_root, must_exist=True)
    if count < 1:
        raise ConfigurationError("scale count 必须为正整数")
    receipt, path = _promotion(root, selection)
    return CommandResult(
        status="confirmation-required",
        phase="scale",
        project_id=receipt.project_id,
        run_id=receipt.pilot_run_id,
        artifacts=(path,),
        evidence=(_resource_evidence("scale", count, strategies=len(receipt.strategy_ids)),),
        next_actions=(
            NextAction(
                command=(
                    f"easydesign scale run {root} --selection {receipt.selection_id} "
                    f"--count {count} --confirm"
                ),
                description="创建独立 production run。",
                approval_required=True,
            ),
        ),
    )


def scale_run(
    project_root: Path, *, selection: str, count: int, confirm: bool, detach: bool = False
) -> CommandResult:
    root = resolve_project_path(project_root, must_exist=True)
    receipt, receipt_path = _promotion(root, selection)
    if not confirm:
        return scale_plan(root, selection=selection, count=count)
    pilot = _run_by_id(root, receipt.pilot_run_id)
    resolved, _ = load_resolved_run_config(pilot.path)
    stage02 = resolved.user_config.stage02
    stage03 = resolved.user_config.stage03
    stage04 = resolved.user_config.stage04
    stage05 = resolved.user_config.stage05
    if stage02 is None or stage03 is None or stage04 is None or stage05 is None:
        raise ConfigurationError("pilot frozen config 缺少 production 前缀")
    config = _config_from_base(
        resolved.user_config,
        stop_after=6,
        stages={
            2: stage02,
            3: stage03,
            4: stage04,
            5: stage05,
            6: Stage06Config(
                total_candidate_count=count,
                allocation_policy="equal-across-promoted-v1",
                preauthorized_candidate_limit=count,
                human_promoted_strategy_ids=receipt.strategy_ids,
                human_promotion_receipt_sha256=sha256_file(receipt_path),
            ),
        },
    )
    run_id = _new_run_id("production")
    result, _ = _launch(
        root,
        phase="scale",
        config=config,
        internal_start=6,
        base=pilot,
        run_id=run_id,
        detach=detach,
    )
    return result.model_copy(
        update={
            "artifacts": (*result.artifacts, receipt_path),
            "next_actions": (
                NextAction(
                    command=f"easydesign select plan {root} --run {run_id}",
                    description="核对最终 Top 200 选择。",
                ),
            ),
        }
    )


def select_plan(project_root: Path, *, run_id: str, top: int = 200) -> CommandResult:
    root = resolve_project_path(project_root, must_exist=True)
    if top < 1:
        raise ConfigurationError("top 必须为正整数")
    run = _run_by_id(root, run_id)
    if 6 not in completed_steps(run.path):
        raise ConfigurationError("select 需要完成的 production run")
    return CommandResult(
        status="confirmation-required",
        phase="select",
        project_id=run.project_id,
        run_id=run.run_id,
        manifest=run.latest_manifest,
        evidence=(
            EvidenceItem(
                kind="selection-plan",
                identity=f"top-{top}",
                status="planned",
                metadata={"requested_top": top, "padding": False, "backend": "protenix-v2 + tnp"},
            ),
        ),
        next_actions=(
            NextAction(
                command=f"easydesign select run {root} --run {run_id} --top {top} --confirm",
                description="只交付真实合法候选，不重复、不补齐。",
                approval_required=True,
            ),
        ),
    )


def select_run(
    project_root: Path, *, run_id: str, top: int, confirm: bool, detach: bool = False
) -> CommandResult:
    root = resolve_project_path(project_root, must_exist=True)
    if not confirm:
        return select_plan(root, run_id=run_id, top=top)
    production = _run_by_id(root, run_id)
    resolved, _ = load_resolved_run_config(production.path)
    stages: dict[int, BaseModel] = {}
    for number in range(2, 7):
        value = getattr(resolved.user_config, f"stage{number:02d}")
        if value is None:
            raise ConfigurationError("production config 前缀不完整")
        stages[number] = value
    stages[7] = Stage07Config(primary_count=top, backup_count=0)
    config = _config_from_base(resolved.user_config, stop_after=7, stages=stages)
    result, _ = _launch(
        root,
        phase="select",
        config=config,
        internal_start=7,
        base=production,
        run_id=production.run_id,
        detach=detach,
    )
    return result.model_copy(
        update={
            "next_actions": (
                NextAction(
                    command=f"easydesign view {root} --run {run_id}",
                    description="只读查看最终 evidence。",
                ),
            )
        }
    )


def job_status(project_root: Path, *, run_id: str | None = None) -> CommandResult:
    root = resolve_project_path(project_root, must_exist=True)
    project_id = _project_id(root)
    controller = LocalStepJobController()
    job = controller.latest(project_id)
    if job is not None and (run_id is None or job.run_id == run_id):
        phase = _phase_for_internal_step(job.step)
        return CommandResult(
            status=job.status,
            phase=phase,
            project_id=project_id,
            run_id=job.run_id,
            job_id=job.job_id,
            manifest=job.run_manifest,
            warnings=(() if job.error is None else (job.error,)),
        )
    return project_status(root)


def _phase_for_internal_step(step: int) -> ResearchPhase:
    if step <= 2:
        return "prepare"
    if step <= 5:
        return "pilot"
    if step == 6:
        return "scale"
    return "select"


def job_watch(project_root: Path, *, run_id: str | None = None) -> CommandResult:
    root = resolve_project_path(project_root, must_exist=True)
    controller = LocalStepJobController()
    job = controller.latest(_project_id(root))
    if job is None or (run_id is not None and job.run_id != run_id):
        raise ConfigurationError("项目没有匹配 local job")
    observed = wait_or_detach(controller, job, detach=False)
    return CommandResult(
        status=observed.status,
        phase=_phase_for_internal_step(observed.step),
        project_id=observed.project_id,
        run_id=observed.run_id,
        job_id=observed.job_id,
        manifest=observed.run_manifest,
    )


def job_resume(
    project_root: Path, *, run_id: str | None = None, detach: bool = False
) -> CommandResult:
    root = resolve_project_path(project_root, must_exist=True)
    controller = LocalStepJobController()
    latest = controller.latest(_project_id(root))
    if latest is not None and latest.status in ACTIVE_JOB_STATUSES:
        observed = wait_or_detach(controller, latest, detach=detach)
        return CommandResult(
            status=observed.status,
            phase=_phase_for_internal_step(observed.step),
            project_id=observed.project_id,
            run_id=observed.run_id,
            job_id=observed.job_id,
            manifest=observed.run_manifest,
        )
    run = _run_by_id(root, run_id) if run_id else _runs(root)[-1]
    if run.status != "running":
        raise ConfigurationError("只有 running 长任务可 resume")
    next_internal = max(completed_steps(run.path), default=0) + 1
    if next_internal not in {4, 5, 6, 7}:
        raise ConfigurationError("当前 run 没有可恢复的长任务")
    job = controller.launch(
        operation="resume",
        project_id=run.project_id,
        project_root=root,
        step=next_internal,
        run_id=run.run_id,
        run_root=run.path,
    )
    observed = wait_or_detach(controller, job, detach=detach)
    return CommandResult(
        status=observed.status,
        phase=_phase_for_internal_step(observed.step),
        project_id=observed.project_id,
        run_id=observed.run_id,
        job_id=observed.job_id,
        manifest=observed.run_manifest,
    )


def job_drain(project_root: Path, *, job_id: str | None = None) -> CommandResult:
    root = resolve_project_path(project_root, must_exist=True)
    controller = LocalStepJobController()
    job = controller.latest(_project_id(root)) if job_id is None else controller.load(job_id)
    if job is None:
        raise ConfigurationError("项目没有 local job")
    drained = controller.request_drain(job.job_id)
    return CommandResult(
        status=drained.status,
        phase=_phase_for_internal_step(drained.step),
        project_id=drained.project_id,
        run_id=drained.run_id,
        job_id=drained.job_id,
        manifest=drained.run_manifest,
    )


__all__ = [
    "CommandResult",
    "ResearchStrategy",
    "initialize_research_project",
    "job_drain",
    "job_resume",
    "job_status",
    "job_watch",
    "pilot_plan",
    "pilot_promote",
    "pilot_review",
    "pilot_run",
    "project_status",
    "scale_plan",
    "scale_run",
    "select_plan",
    "select_run",
    "site_approve",
    "site_propose",
    "site_scan",
    "strategy_draft",
    "strategy_freeze",
    "strategy_validate",
    "target_approve",
    "target_prepare",
]
