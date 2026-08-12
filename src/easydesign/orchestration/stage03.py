"""Stage 03 manifest-only BoltzGen strategy compilation."""

from __future__ import annotations

import json
import shutil
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

import yaml  # type: ignore[import-untyped]
from pydantic import BaseModel, ConfigDict

import easydesign
from easydesign.backends.boltzgen import BoltzGenCheckAdapter
from easydesign.core import (
    ArtifactRef,
    Attempt,
    CodeIdentity,
    ErrorInfo,
    ExecutionStatus,
    ManifestStateError,
    RunManifest,
    RuntimeProfileRef,
    StageId,
    StageManifest,
    dump_model,
    load_model,
    sha256_file,
)
from easydesign.core.timestamps import normalize_aware_datetime
from easydesign.safe_writes import (
    append_pointer_revision,
    quarantine_if_workspace_path,
    read_last_text_line,
)
from easydesign.stages.s02_hotspot_discovery import HotspotsFile
from easydesign.stages.s03_boltzgen_configuration import (
    StrategyBundle,
    compile_basic_vhh_matrix,
    compile_vhh_strategy_plan,
    write_design_matrix,
)

from .config import load_run_config
from .workspace import (
    PreparedRun,
    ResolvedRunConfig,
    RunIndexEntry,
    RunWorkspace,
    initialize_run_workspace,
    load_resolved_run_config,
    upsert_run_index_entries,
)


class Stage03Execution(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    status: str
    run_root: Path
    run_manifest: Path
    stage_manifest: Path
    strategy_bundle: Path
    strategy_count: int


@dataclass(frozen=True, slots=True)
class _Upstream:
    run: RunManifest
    run_manifest_path: Path
    stage01: StageManifest
    stage02: StageManifest
    target_bundle_ref: ArtifactRef
    target_structure_ref: ArtifactRef
    hotspots_ref: ArtifactRef
    stage02_manifest_ref: ArtifactRef


def _latest_manifest(root: Path) -> tuple[RunManifest, Path]:
    pointer = root / "manifests" / "LATEST"
    try:
        name = read_last_text_line(pointer)
    except OSError as error:
        raise ManifestStateError(f"无法读取 RunManifest LATEST: {pointer}") from error
    path = root / "manifests" / name
    return load_model(path, RunManifest), path


def _load_upstream(root: Path) -> _Upstream:
    run, run_path = _latest_manifest(root)
    by_stage = {reference.producer_stage: reference for reference in run.stage_manifest_refs}
    stage01_ref = by_stage.get(str(StageId.TARGET_PREPARATION))
    stage02_ref = by_stage.get(str(StageId.HOTSPOT_DISCOVERY))
    if stage01_ref is None or stage02_ref is None:
        raise ManifestStateError("Stage 03 必须同时获得当前 Stage 01/02 manifest")
    stage01_path = stage01_ref.verify(root)
    stage02_path = stage02_ref.verify(root)
    stage01 = load_model(stage01_path, StageManifest)
    stage02 = load_model(stage02_path, StageManifest)
    if stage01.status is not ExecutionStatus.SUCCEEDED:
        raise ManifestStateError("Stage 01 未成功，不能执行 Stage 03")
    if stage02.status is not ExecutionStatus.SUCCEEDED:
        raise ManifestStateError("Stage 02 未成功，不能执行 Stage 03")
    stage02.validate_inputs_declared_by((stage01,))
    target_bundle = stage01.require_output("target-bundle")
    target_structure = stage01.require_output("target-structure")
    hotspots = stage02.require_output("hotspots")
    target_bundle.verify(root)
    target_structure.verify(root)
    hotspots.verify(root)
    return _Upstream(
        run=run,
        run_manifest_path=run_path,
        stage01=stage01,
        stage02=stage02,
        target_bundle_ref=target_bundle,
        target_structure_ref=target_structure,
        hotspots_ref=hotspots,
        stage02_manifest_ref=stage02_ref,
    )


def _atomic_text(text: str, path: Path) -> None:
    append_pointer_revision(path, text)


def _json_file(payload: object, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("x", encoding="utf-8", newline="\n") as handle:
            json.dump(
                payload,
                handle,
                ensure_ascii=False,
                allow_nan=False,
                indent=2,
                sort_keys=True,
            )
            handle.write("\n")
    except FileExistsError as error:
        raise ManifestStateError(f"Stage 03 禁止覆盖 artifact: {path}") from error
    return path


def _artifact(
    root: Path,
    path: Path,
    *,
    artifact_id: str,
    role: str,
    file_format: str,
    attempt_id: str = "attempt-0001",
) -> ArtifactRef:
    return ArtifactRef.from_file(
        run_root=root,
        relative_path=path.relative_to(root).as_posix(),
        artifact_id=artifact_id,
        role=role,
        file_format=file_format,
        producer_stage=str(StageId.BOLTZGEN_CONFIGURATION),
        producer_attempt=attempt_id,
    )


def _publish_run_manifest(
    root: Path,
    current: RunManifest,
    *,
    stage_manifest_ref: ArtifactRef,
    stop_after_stage: int,
    now: datetime,
) -> Path:
    by_stage = {reference.producer_stage: reference for reference in current.stage_manifest_refs}
    by_stage[str(StageId.BOLTZGEN_CONFIGURATION)] = stage_manifest_ref
    terminal = stop_after_stage == 3
    timestamp = now if now > current.updated_at else current.updated_at + timedelta(microseconds=1)
    next_manifest = current.next_revision(
        updated_at=timestamp,
        status=ExecutionStatus.SUCCEEDED if terminal else ExecutionStatus.RUNNING,
        completed_at=timestamp if terminal else None,
        stage_manifest_refs=tuple(
            by_stage[key] for key in sorted(key for key in by_stage if key is not None)
        ),
        clear_workflow_state=True,
    )
    path = root / "manifests" / f"run-manifest.v{next_manifest.revision:04d}.json"
    dump_model(next_manifest, path)
    _atomic_text(path.name + "\n", root / "manifests" / "LATEST")
    return path


def initialize_continuation_run(
    *,
    source_run_root: Path,
    config_path: Path,
    runs_root: Path,
    run_id: str,
    code_identity: CodeIdentity,
    runtime_profile: RuntimeProfileRef,
    created_at: datetime | None = None,
    copy_through_stage: int | None = None,
) -> PreparedRun:
    """Fork an immutable succeeded handoff into the next configured stage."""

    source = source_run_root.resolve()
    source_run, source_run_manifest_path = _latest_manifest(source)
    if copy_through_stage is None and source_run.status is not ExecutionStatus.SUCCEEDED:
        raise ManifestStateError("continuation source 必须是终态 succeeded run")
    loaded = load_run_config(config_path)
    if loaded.config.project_id != source_run.project_id:
        raise ManifestStateError("continuation config project_id 必须与 source run 一致")
    source_stage_refs = tuple(
        reference
        for reference in source_run.stage_manifest_refs
        if copy_through_stage is None
        or (
            reference.producer_stage is not None
            and int(reference.producer_stage.split("-", maxsplit=1)[0]) <= copy_through_stage
        )
    )
    if not source_stage_refs:
        raise ManifestStateError("continuation source 没有已完成 Stage")
    stage_numbers: list[int] = []
    copied_stage_sha256: dict[str, str] = {}
    for reference in source_stage_refs:
        if reference.producer_stage is None:
            raise ManifestStateError("continuation source StageManifest 缺少 producer_stage")
        stage_number = int(reference.producer_stage.split("-", maxsplit=1)[0])
        manifest = load_model(reference.verify(source), StageManifest)
        if manifest.status is not ExecutionStatus.SUCCEEDED:
            raise ManifestStateError(f"continuation source Stage {stage_number:02d} 未成功")
        stage_numbers.append(stage_number)
        copied_stage_sha256[reference.producer_stage] = reference.sha256
    ordered_numbers = sorted(stage_numbers)
    expected_last = copy_through_stage if copy_through_stage is not None else max(ordered_numbers)
    if ordered_numbers != list(range(1, expected_last + 1)):
        raise ManifestStateError("continuation source Stage 序列不连续")
    next_stage = expected_last + 1
    if loaded.config.workflow.stop_after_stage < next_stage:
        raise ManifestStateError("continuation config 没有启用 source 之后的下一 Stage")
    timestamp = datetime.now(UTC) if created_at is None else normalize_aware_datetime(created_at)
    prepared = initialize_run_workspace(
        config_path=config_path,
        runs_root=runs_root,
        easydesign_version=easydesign.__version__,
        code_identity=code_identity,
        runtime_profile=runtime_profile,
        run_id=run_id,
        created_at=timestamp,
    )
    destination = prepared.workspace.run_root
    try:
        for reference in source_stage_refs:
            assert reference.producer_stage is not None
            source_stage = source / reference.producer_stage
            destination_stage = destination / reference.producer_stage
            shutil.copytree(source_stage, destination_stage, dirs_exist_ok=True)
        source_input = source / "input-snapshot"
        if source_input.is_dir():
            shutil.copytree(
                source_input,
                destination / "input-snapshot",
                dirs_exist_ok=True,
            )
        source_record = _json_file(
            {
                "schema_version": "0.1",
                "source_project_id": source_run.project_id,
                "source_run_id": source_run.run_id,
                "source_run_manifest_sha256": sha256_file(source_run_manifest_path),
                "source_run_manifest_revision": source_run.revision,
                "next_stage": next_stage,
                "copied_stage_manifest_sha256": copied_stage_sha256,
            },
            destination / "config-snapshot" / "continuation-source.json",
        )
        if not source_record.is_file():
            raise ManifestStateError("continuation source record 未创建")
        copied_refs = source_stage_refs
        for reference in copied_refs:
            reference.verify(destination)
        current, _ = _latest_manifest(destination)
        next_time = (
            timestamp
            if timestamp > current.updated_at
            else current.updated_at + timedelta(microseconds=1)
        )
        continued = current.next_revision(
            updated_at=next_time,
            status=ExecutionStatus.RUNNING,
            stage_manifest_refs=copied_refs,
        )
        manifest_path = destination / "manifests" / f"run-manifest.v{continued.revision:04d}.json"
        dump_model(continued, manifest_path)
        _atomic_text(
            manifest_path.name + "\n",
            destination / "manifests" / "LATEST",
        )
        upsert_run_index_entries(
            prepared.workspace.runs_root,
            (
                RunIndexEntry(
                    category="project-run",
                    path=destination.relative_to(prepared.workspace.runs_root).as_posix(),
                    layout_version="1",
                    status="running",
                    project_id=prepared.workspace.project_id,
                    run_id=prepared.workspace.run_id,
                    notes=("Continued from a checksum-verified succeeded upstream run.",),
                ),
            ),
            generated_at=next_time,
        )
    except Exception:
        if destination.exists():
            quarantine_if_workspace_path(
                destination,
                operation="initialize-continuation-run",
                reason="continuation run 初始化失败",
            )
        raise
    _, latest_path = _latest_manifest(destination)
    return PreparedRun(
        loaded_config=prepared.loaded_config,
        workspace=prepared.workspace.__class__(
            runs_root=prepared.workspace.runs_root,
            run_root=prepared.workspace.run_root,
            project_id=prepared.workspace.project_id,
            run_id=prepared.workspace.run_id,
            config_snapshot=prepared.workspace.config_snapshot,
            input_snapshot=prepared.workspace.input_snapshot,
            resolved_config=prepared.workspace.resolved_config,
            run_manifest=latest_path,
            latest_manifest_pointer=prepared.workspace.latest_manifest_pointer,
        ),
    )


def _assert_completed_configuration_unchanged(
    *,
    root: Path,
    previous: ResolvedRunConfig,
    loaded: object,
    completed_through_stage: int,
) -> None:
    """阻止同 run continuation 偷改已经完成的科学输入或配置。"""

    current_config = getattr(loaded, "config", None)
    if current_config is None:
        raise ManifestStateError("continuation config 未解析为 EasyDesign 配置")
    if current_config.design != previous.user_config.design:
        raise ManifestStateError("修改 design 必须创建分支 run")
    if (
        current_config.workflow.max_strategy_rounds
        != previous.user_config.workflow.max_strategy_rounds
    ):
        raise ManifestStateError("修改已冻结的策略轮次必须创建分支 run")

    previous_stage01 = previous.user_config.stage01.model_dump(mode="python")
    current_stage01 = current_config.stage01.model_dump(mode="python")
    previous_source = previous_stage01["target"]["source"]
    current_source = current_stage01["target"]["source"]
    if previous_source.get("type") != current_source.get("type"):
        raise ManifestStateError("修改 Stage 01 source 类型必须创建分支 run")
    ignored_source_keys = {"path", "source_run_root"}
    for key in ignored_source_keys:
        previous_source.pop(key, None)
        current_source.pop(key, None)
    previous_prediction = previous_stage01.get("structure_prediction")
    current_prediction = current_stage01.get("structure_prediction")
    if isinstance(previous_prediction, dict) and isinstance(current_prediction, dict):
        previous_msa = previous_prediction.get("msa")
        current_msa = current_prediction.get("msa")
        if isinstance(previous_msa, dict) and isinstance(current_msa, dict):
            previous_msa.pop("path", None)
            current_msa.pop("path", None)
    if previous_stage01 != current_stage01:
        raise ManifestStateError("修改已完成 Stage 01 配置必须创建分支 run")

    source_path = getattr(loaded, "source_path", None)
    if source_path is not None:
        input_snapshot = previous.input_snapshot.verify(root)
        if sha256_file(Path(source_path)) != sha256_file(input_snapshot):
            raise ManifestStateError("continuation 输入与冻结 Stage 01 输入不一致")
    precomputed_msa_path = getattr(loaded, "precomputed_msa_path", None)
    if precomputed_msa_path is not None:
        if previous.precomputed_msa_snapshot is None:
            raise ManifestStateError("continuation 新增预计算 MSA 必须创建分支 run")
        previous_msa_snapshot = previous.precomputed_msa_snapshot.verify(root)
        if sha256_file(Path(precomputed_msa_path)) != sha256_file(previous_msa_snapshot):
            raise ManifestStateError("continuation MSA 与冻结输入不一致")

    for stage_number in range(2, completed_through_stage + 1):
        field_name = f"stage{stage_number:02d}"
        if getattr(current_config, field_name) != getattr(
            previous.user_config,
            field_name,
        ):
            raise ManifestStateError(f"修改已完成 Stage {stage_number:02d} 配置必须创建分支 run")


def continue_run_in_place(
    *,
    source_run_root: Path,
    config_path: Path,
    code_identity: CodeIdentity,
    runtime_profile: RuntimeProfileRef,
    continued_at: datetime | None = None,
    continue_after_stage: int | None = None,
) -> PreparedRun:
    """不复制上游目录，在同一 run 中发布下一阶段配置 revision。"""

    root = source_run_root.resolve()
    current, current_path = _latest_manifest(root)
    if continue_after_stage is None and current.status is not ExecutionStatus.SUCCEEDED:
        raise ManifestStateError("同 run continuation 只接受 succeeded run")
    if continue_after_stage is not None and current.status not in {
        ExecutionStatus.RUNNING,
        ExecutionStatus.SUCCEEDED,
    }:
        raise ManifestStateError("按成功 Stage 前缀继续只接受 running 或 succeeded run")
    loaded = load_run_config(config_path)
    if loaded.config.project_id != current.project_id:
        raise ManifestStateError("continuation config project_id 必须与当前 run 一致")
    stage_numbers = sorted(
        int(reference.producer_stage.split("-", maxsplit=1)[0])
        for reference in current.stage_manifest_refs
        if reference.producer_stage is not None
    )
    if not stage_numbers or stage_numbers != list(range(1, max(stage_numbers) + 1)):
        raise ManifestStateError("同 run continuation 要求 Stage 从 01 连续")
    for reference in current.stage_manifest_refs:
        stage_manifest = load_model(reference.verify(root), StageManifest)
        if stage_manifest.status is not ExecutionStatus.SUCCEEDED:
            raise ManifestStateError(f"同 run continuation 的上游未成功: {stage_manifest.stage_id}")
    completed_through = max(stage_numbers)
    if continue_after_stage is not None and continue_after_stage != completed_through:
        raise ManifestStateError("从较早 Stage 改写流程必须创建分支 run，不能原地 continuation")
    next_stage = completed_through + 1
    if loaded.config.workflow.stop_after_stage < next_stage:
        raise ManifestStateError("continuation config 没有启用下一 Stage")

    previous_resolved, _ = load_resolved_run_config(root)
    _assert_completed_configuration_unchanged(
        root=root,
        previous=previous_resolved,
        loaded=loaded,
        completed_through_stage=completed_through,
    )
    timestamp = (
        datetime.now(UTC) if continued_at is None else normalize_aware_datetime(continued_at)
    )
    if timestamp <= current.updated_at:
        timestamp = current.updated_at + timedelta(microseconds=1)
    revision_number = current.revision + 1
    revisions_root = root / "config-snapshot" / "revisions"
    revision_name = f"revision-{revision_number:04d}"
    revision_root = revisions_root / revision_name
    if revision_root.exists():
        raise ManifestStateError(f"config revision 已存在，拒绝覆盖: {revision_root}")
    revisions_root.mkdir(parents=True, exist_ok=True)
    staging = Path(
        tempfile.mkdtemp(
            prefix=f".{revision_name}.creating-",
            dir=revisions_root,
        )
    )
    try:
        config_copy = staging / "easydesign.yaml"
        shutil.copyfile(loaded.config_path, config_copy)
        resolved = previous_resolved.model_copy(
            update={
                "user_config": loaded.config,
                "stop_after_stage": loaded.config.workflow.stop_after_stage,
                "runtime_profile": runtime_profile,
            }
        )
        resolved_copy = staging / "resolved-config.json"
        dump_model(resolved, resolved_copy)
        _json_file(
            {
                "schema_version": "0.1",
                "mode": "same-run-stage-continuation",
                "project_id": current.project_id,
                "run_id": current.run_id,
                "completed_through_stage": completed_through,
                "next_stage": next_stage,
                "previous_run_manifest": current_path.name,
                "previous_run_manifest_sha256": sha256_file(current_path),
                "continued_at": timestamp.isoformat(),
            },
            staging / "continuation.json",
        )
        staging.rename(revision_root)
    except Exception:
        if staging.exists():
            quarantine_if_workspace_path(
                staging,
                operation="publish-config-revision",
                reason="配置 revision 发布失败",
            )
        raise

    config_path_in_run = revision_root / "easydesign.yaml"
    resolved_path_in_run = revision_root / "resolved-config.json"
    config_ref = ArtifactRef.from_file(
        run_root=root,
        relative_path=config_path_in_run.relative_to(root).as_posix(),
        artifact_id="run-config",
        role="user-config-snapshot",
        file_format="yaml",
    )
    continuation = (
        current.continue_after_success
        if continue_after_stage is None
        else current.continue_with_config
    )
    continued = continuation(
        updated_at=timestamp,
        config_snapshot=config_ref,
        easydesign_version=easydesign.__version__,
        code_identity=code_identity,
        runtime_profile=runtime_profile,
    )
    manifest_path = root / "manifests" / f"run-manifest.v{continued.revision:04d}.json"
    try:
        dump_model(continued, manifest_path)
        _atomic_text(
            f"revisions/{revision_name}/resolved-config.json\n",
            root / "config-snapshot" / "CURRENT",
        )
        _atomic_text(manifest_path.name + "\n", root / "manifests" / "LATEST")
    except Exception:
        revision_root.rename(revisions_root / f".{revision_name}.unpublished")
        raise
    runs_root = root.parents[1]
    upsert_run_index_entries(
        runs_root,
        (
            RunIndexEntry(
                category="project-run",
                path=root.relative_to(runs_root).as_posix(),
                layout_version="2",
                status="running",
                project_id=current.project_id,
                run_id=current.run_id,
                notes=(
                    f"Continued in place from Stage {completed_through:02d} "
                    f"to Stage {next_stage:02d}.",
                ),
            ),
        ),
        generated_at=timestamp,
    )
    workspace = RunWorkspace(
        runs_root=runs_root,
        run_root=root,
        project_id=current.project_id,
        run_id=current.run_id,
        config_snapshot=config_path_in_run,
        input_snapshot=previous_resolved.input_snapshot.verify(root),
        resolved_config=resolved_path_in_run,
        run_manifest=manifest_path,
        latest_manifest_pointer=root / "manifests" / "LATEST",
    )
    return PreparedRun(loaded_config=loaded, workspace=workspace)


def execute_stage03(
    *,
    run_root: Path,
    adapter: BoltzGenCheckAdapter,
    executed_at: datetime | None = None,
) -> Stage03Execution:
    root = run_root.resolve()
    upstream = _load_upstream(root)
    if upstream.run.status is not ExecutionStatus.RUNNING:
        raise ManifestStateError("Stage 03 只能写入 running run")
    if any(
        reference.producer_stage == str(StageId.BOLTZGEN_CONFIGURATION)
        for reference in upstream.run.stage_manifest_refs
    ):
        raise ManifestStateError("Stage 03 已发布，禁止覆盖")
    resolved_config, _ = load_resolved_run_config(root)
    config = resolved_config.user_config.stage03
    if config is None:
        raise ManifestStateError("run config 没有 Stage 03 配置")
    now = datetime.now(UTC) if executed_at is None else normalize_aware_datetime(executed_at)
    attempt_id = "attempt-0001"
    attempt_root = root / str(StageId.BOLTZGEN_CONFIGURATION) / attempt_id
    artifacts = attempt_root / "artifacts"
    logs = attempt_root / "logs"
    logs.mkdir(parents=True, exist_ok=False)
    hotspots = HotspotsFile.model_validate(
        yaml.safe_load(upstream.hotspots_ref.verify(root).read_text(encoding="utf-8"))
    )
    target = upstream.target_structure_ref.verify(root)

    capability = adapter.probe()
    explicit_plan = config.variants is not None or bool(config.native_variants)
    if explicit_plan:
        scaffold_assets, strategies = compile_vhh_strategy_plan(
            target_cif=target,
            hotspots=hotspots,
            artifacts_root=artifacts,
            variants=config.variants or (),
            native_variants=config.native_variants,
        )
    else:
        scaffold_assets, strategies = compile_basic_vhh_matrix(
            target_cif=target,
            hotspots=hotspots,
            artifacts_root=artifacts,
            candidates_per_strategy=config.candidates_per_strategy,
            scaffold_ids=config.scaffold_ids,
        )
    _json_file(capability, artifacts / "boltzgen-capability.json")
    report = adapter.validate(
        artifacts_root=artifacts,
        strategies=strategies,
        logs_root=logs / "validation",
        checked_at=now,
    )
    report_path = artifacts / "validation-report.json"
    dump_model(report, report_path)
    if report.status != "passed":
        failed_ids = tuple(item.strategy_id for item in report.items if item.status == "failed")
        report_ref = _artifact(
            root,
            report_path,
            artifact_id="strategy-validation",
            role="backend-log",
            file_format="json",
        )
        failed_log_refs: list[ArtifactRef] = [report_ref]
        for item in report.items:
            assert item.stdout_path is not None
            assert item.stderr_path is not None
            failed_log_refs.extend(
                (
                    _artifact(
                        root,
                        logs / "validation" / item.stdout_path,
                        artifact_id=f"validation-{item.strategy_id}-stdout",
                        role="backend-log",
                        file_format="text",
                    ),
                    _artifact(
                        root,
                        logs / "validation" / item.stderr_path,
                        artifact_id=f"validation-{item.strategy_id}-stderr",
                        role="backend-log",
                        file_format="text",
                    ),
                )
            )
        failed_attempt = Attempt(
            attempt_id=attempt_id,
            status=ExecutionStatus.FAILED,
            created_at=now,
            started_at=now,
            ended_at=now,
            backend_name="boltzgen",
            backend_version="0.3.2",
            executor_name="easydesign-local",
            log_artifacts=tuple(failed_log_refs),
            error=ErrorInfo(
                code="boltzgen-validation-failed",
                message=(
                    "BoltzGen design specification validation failed: " + ", ".join(failed_ids)
                )[:4096],
                retryable=False,
            ),
        )
        dump_model(failed_attempt, attempt_root / "attempt-manifest.json")
        failed_stage = StageManifest(
            stage_id=StageId.BOLTZGEN_CONFIGURATION,
            contract_version="0.1",
            status=ExecutionStatus.FAILED,
            created_at=now,
            completed_at=now,
            input_artifacts=(
                upstream.target_bundle_ref,
                upstream.target_structure_ref,
                upstream.hotspots_ref,
            ),
            attempts=(failed_attempt,),
            warnings=("No StrategyBundle was published.",),
        )
        failed_stage.validate_inputs_declared_by((upstream.stage01, upstream.stage02))
        failed_stage_path = artifacts / "stage-manifest.json"
        dump_model(failed_stage, failed_stage_path)
        failed_stage_ref = _artifact(
            root,
            failed_stage_path,
            artifact_id="stage-03-manifest",
            role="stage-manifest",
            file_format="json",
        )
        failed_time = (
            now
            if now > upstream.run.updated_at
            else upstream.run.updated_at + timedelta(microseconds=1)
        )
        failed_run = upstream.run.next_revision(
            updated_at=failed_time,
            status=ExecutionStatus.FAILED,
            completed_at=failed_time,
            stage_manifest_refs=(
                *upstream.run.stage_manifest_refs,
                failed_stage_ref,
            ),
            clear_workflow_state=True,
        )
        failed_run_path = root / "manifests" / f"run-manifest.v{failed_run.revision:04d}.json"
        dump_model(failed_run, failed_run_path)
        _atomic_text(
            failed_run_path.name + "\n",
            root / "manifests" / "LATEST",
        )
        raise ManifestStateError("BoltzGen design specification 校验失败；已发布终态失败 manifest")
    write_design_matrix(
        strategies,
        json_path=artifacts / "design-matrix.json",
        tsv_path=artifacts / "design-matrix.tsv",
    )
    _json_file(
        {
            "schema_version": "0.1",
            "registry_id": config.scaffold_registry,
            "license_path": "assets/scaffolds/BOLTZGEN_LICENSE.txt",
            "assets": [asset.model_dump(mode="json") for asset in scaffold_assets],
        },
        artifacts / "scaffold-resolution.json",
    )
    bundle = StrategyBundle(
        schema_version="0.3" if explicit_plan else "0.1",
        generated_at=now,
        project_id=upstream.run.project_id,
        run_id=upstream.run.run_id,
        target_id=hotspots.target_id,
        target_structure_sha256=upstream.target_structure_ref.sha256,
        target_bundle_sha256=upstream.target_bundle_ref.sha256,
        hotspots_sha256=upstream.hotspots_ref.sha256,
        source_stage02_manifest_sha256=upstream.stage02_manifest_ref.sha256,
        validation_report_sha256=sha256_file(report_path),
        scaffold_assets=scaffold_assets,
        strategies=strategies,
    )
    bundle_path = artifacts / "strategy-bundle.json"
    dump_model(bundle, bundle_path)
    stdout_path = logs / "stdout.log"
    stderr_path = logs / "stderr.log"
    stdout_path.write_text(
        f"Compiled {len(strategies)} strategies; all BoltzGen checks passed.\n",
        encoding="utf-8",
    )
    stderr_path.write_text("", encoding="utf-8")

    output_refs = [
        _artifact(
            root,
            bundle_path,
            artifact_id="strategy-bundle",
            role="stage04-strategy-input",
            file_format="json",
        ),
        _artifact(
            root,
            artifacts / "design-matrix.json",
            artifact_id="design-matrix",
            role="strategy-matrix",
            file_format="json",
        ),
        _artifact(
            root,
            artifacts / "design-matrix.tsv",
            artifact_id="design-matrix-tsv",
            role="human-readable-strategy-matrix",
            file_format="tsv",
        ),
        _artifact(
            root,
            report_path,
            artifact_id="strategy-validation",
            role="backend-validation",
            file_format="json",
        ),
        _artifact(
            root,
            artifacts / "scaffold-resolution.json",
            artifact_id="scaffold-resolution",
            role="scaffold-provenance",
            file_format="json",
        ),
        _artifact(
            root,
            artifacts / "boltzgen-capability.json",
            artifact_id="boltzgen-capability",
            role="backend-capability",
            file_format="json",
        ),
        _artifact(
            root,
            artifacts / "assets" / "target.cif",
            artifact_id="strategy-target",
            role="portable-strategy-target",
            file_format="mmcif",
        ),
    ]
    for scaffold in scaffold_assets:
        output_refs.extend(
            (
                _artifact(
                    root,
                    artifacts / scaffold.specification_path,
                    artifact_id=f"scaffold-{scaffold.scaffold_id}-spec",
                    role="vhh-scaffold-specification",
                    file_format="yaml",
                ),
                _artifact(
                    root,
                    artifacts / scaffold.structure_path,
                    artifact_id=f"scaffold-{scaffold.scaffold_id}-structure",
                    role="vhh-scaffold-structure",
                    file_format="mmcif",
                ),
            )
        )
    output_refs.append(
        _artifact(
            root,
            artifacts / "assets" / "scaffolds" / "BOLTZGEN_LICENSE.txt",
            artifact_id="boltzgen-scaffold-license",
            role="third-party-license",
            file_format="text",
        )
    )
    for strategy in strategies:
        output_refs.extend(
            (
                _artifact(
                    root,
                    artifacts / strategy.design_specification_path,
                    artifact_id=f"strategy-{strategy.strategy_id}",
                    role="boltzgen-design-specification",
                    file_format="yaml",
                ),
                _artifact(
                    root,
                    artifacts / "strategies" / strategy.strategy_id / "strategy-manifest.json",
                    artifact_id=f"strategy-{strategy.strategy_id}-manifest",
                    role="strategy-manifest",
                    file_format="json",
                ),
            )
        )
        if strategy.variant_scaffold_path is not None:
            output_refs.append(
                _artifact(
                    root,
                    artifacts / strategy.variant_scaffold_path,
                    artifact_id=f"strategy-{strategy.strategy_id}-scaffold",
                    role="variant-scaffold-specification",
                    file_format="yaml",
                )
            )
    stdout_ref = _artifact(
        root,
        stdout_path,
        artifact_id="stage03-stdout",
        role="backend-log",
        file_format="text",
    )
    stderr_ref = _artifact(
        root,
        stderr_path,
        artifact_id="stage03-stderr",
        role="backend-log",
        file_format="text",
    )
    validation_log_refs: list[ArtifactRef] = []
    for item in report.items:
        assert item.stdout_path is not None
        assert item.stderr_path is not None
        validation_log_refs.extend(
            (
                _artifact(
                    root,
                    logs / "validation" / item.stdout_path,
                    artifact_id=f"validation-{item.strategy_id}-stdout",
                    role="backend-log",
                    file_format="text",
                ),
                _artifact(
                    root,
                    logs / "validation" / item.stderr_path,
                    artifact_id=f"validation-{item.strategy_id}-stderr",
                    role="backend-log",
                    file_format="text",
                ),
            )
        )
    attempt = Attempt(
        attempt_id=attempt_id,
        status=ExecutionStatus.SUCCEEDED,
        created_at=now,
        started_at=now,
        ended_at=now,
        backend_name="boltzgen",
        backend_version="0.3.2",
        executor_name="easydesign-local",
        log_artifacts=(
            stdout_ref,
            stderr_ref,
            *validation_log_refs,
        ),
    )
    dump_model(attempt, attempt_root / "attempt-manifest.json")
    stage_manifest = StageManifest(
        stage_id=StageId.BOLTZGEN_CONFIGURATION,
        contract_version="0.1",
        status=ExecutionStatus.SUCCEEDED,
        created_at=now,
        completed_at=now,
        input_artifacts=(
            upstream.target_bundle_ref,
            upstream.target_structure_ref,
            upstream.hotspots_ref,
        ),
        output_artifacts=tuple(output_refs),
        attempts=(attempt,),
        selected_attempt_id=attempt_id,
        warnings=(
            (
                "Explicit strategy plan: only declared variants/scaffolds were compiled."
                if explicit_plan
                else "Basic 1.0 template only: H_all + C_full."
            ),
            "Non-hotspot residues remain neutral and are not emitted as not_binding.",
            "BoltzGen 0.3.2 does not expose a reliable deterministic generation seed.",
        ),
    )
    stage_manifest.validate_inputs_declared_by((upstream.stage01, upstream.stage02))
    stage_manifest_path = artifacts / "stage-manifest.json"
    dump_model(stage_manifest, stage_manifest_path)
    stage_ref = _artifact(
        root,
        stage_manifest_path,
        artifact_id="stage-03-manifest",
        role="stage-manifest",
        file_format="json",
    )
    run_manifest = _publish_run_manifest(
        root,
        upstream.run,
        stage_manifest_ref=stage_ref,
        stop_after_stage=resolved_config.stop_after_stage,
        now=now,
    )
    upsert_run_index_entries(
        root.parents[1],
        (
            RunIndexEntry(
                category="project-run",
                path=root.relative_to(root.parents[1]).as_posix(),
                layout_version="1",
                status=("succeeded" if resolved_config.stop_after_stage == 3 else "running"),
                project_id=upstream.run.project_id,
                run_id=upstream.run.run_id,
                notes=(f"Stage 03 compiled {len(strategies)} validated strategies.",),
            ),
        ),
        generated_at=now,
    )
    return Stage03Execution(
        status="succeeded",
        run_root=root,
        run_manifest=run_manifest,
        stage_manifest=stage_manifest_path,
        strategy_bundle=bundle_path,
        strategy_count=len(strategies),
    )
