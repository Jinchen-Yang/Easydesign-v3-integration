"""Flat project files and append-only canonical configuration revisions."""

from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import yaml  # type: ignore[import-untyped]
from pydantic import BaseModel, ConfigDict

from easydesign.core import (
    ConfigurationError,
    ExecutionStatus,
    RunManifest,
    StageManifest,
    load_model,
)
from easydesign.safe_writes import read_last_text_line
from easydesign.workspace_context import WorkspaceContext

from .application import RunSummary, list_runs
from .config import (
    EasyDesignRunConfig,
    Stage01Config,
    Stage02Config,
    Stage03Config,
    Stage04Config,
    Stage05Config,
    Stage06Config,
    Stage07Config,
    load_run_config,
)
from .project import InitializedProject, initialize_project
from .task_tracking import atomic_dump_runtime_model, load_latest_runtime_model
from .workspace import load_resolved_run_config

STAGE_FILENAMES = {
    1: "01-target-preparation.yaml",
    2: "02-hotspot-discovery.yaml",
    3: "03-boltzgen-configuration.yaml",
    4: "04-pilot-generation.yaml",
    5: "05-pilot-filtering.yaml",
    6: "06-scale-generation-and-refolding.yaml",
    7: "07-final-filtering-and-selection.yaml",
}
STAGE_MODELS: dict[int, type[BaseModel]] = {
    1: Stage01Config,
    2: Stage02Config,
    3: Stage03Config,
    4: Stage04Config,
    5: Stage05Config,
    6: Stage06Config,
    7: Stage07Config,
}


class LocalProjectRunBinding(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: str = "0.1"
    project_id: str
    project_root: Path
    run_id: str
    run_root: Path
    updated_at: datetime


def resolve_project_path(value: Path, *, must_exist: bool) -> Path:
    """Resolve only inside this product's projects root.

    A single project name is interpreted below workspace/projects.  Longer
    relative paths are interpreted from the repository root so the documented
    workspace/projects/name form works from any activated VS Code terminal.
    """

    context = WorkspaceContext.discover()
    expanded = value.expanduser()
    if not expanded.is_absolute():
        if len(expanded.parts) == 1:
            expanded = context.projects_root / expanded
        else:
            expanded = context.root / expanded
    resolved = expanded.resolve(strict=must_exist)
    if not resolved.is_relative_to(context.projects_root):
        raise ConfigurationError(
            "本地产品只接受当前 workspace/projects；拒绝旧 UI 或外部项目路径"
        )
    if must_exist and not resolved.is_dir():
        raise ConfigurationError(f"项目目录不存在: {resolved}")
    return resolved


def project_config_path(project_root: Path) -> Path:
    root = resolve_project_path(project_root, must_exist=True)
    pointer = root / "CONFIG_CURRENT"
    try:
        relative = Path(read_last_text_line(pointer))
    except OSError as error:
        raise ConfigurationError(f"项目缺少 CONFIG_CURRENT: {root}") from error
    if relative.is_absolute() or ".." in relative.parts:
        raise ConfigurationError("CONFIG_CURRENT 必须是项目内相对路径")
    selected = (root / relative).resolve(strict=True)
    if not selected.is_relative_to(root):
        raise ConfigurationError("CONFIG_CURRENT 逃出项目目录")
    return selected


def _append_pointer(path: Path, value: str) -> None:
    normalized = value.strip()
    if not normalized or "\n" in normalized or "\r" in normalized:
        raise ConfigurationError("CONFIG_CURRENT revision 必须是单行相对路径")
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(normalized + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def publish_config_revision(project_root: Path, config: EasyDesignRunConfig) -> Path:
    root = resolve_project_path(project_root, must_exist=True)
    revisions = root / "config-revisions"
    revisions.mkdir(parents=True, exist_ok=True)
    existing = sorted(revisions.glob("easydesign.rev-*.yaml"))
    destination = revisions / f"easydesign.rev-{len(existing) + 1:06d}.yaml"
    with destination.open("x", encoding="utf-8", newline="\n") as handle:
        yaml.safe_dump(
            config.model_dump(mode="json", exclude_none=False),
            handle,
            allow_unicode=True,
            sort_keys=False,
        )
    # Resolve local inputs and revalidate the complete public config before
    # making this immutable revision current.
    load_run_config(destination, source_base_dir=root)
    _append_pointer(
        root / "CONFIG_CURRENT",
        destination.relative_to(root).as_posix(),
    )
    return destination


def read_stage_fragment(
    step: int,
    project_root: Path,
    *,
    custom_path: Path | None = None,
) -> BaseModel:
    if step not in STAGE_FILENAMES:
        raise ConfigurationError("STEP 必须是 1–7")
    root = resolve_project_path(project_root, must_exist=True)
    selected = root / STAGE_FILENAMES[step] if custom_path is None else custom_path.expanduser()
    selected = selected.resolve(strict=True)
    if not selected.is_file():
        raise ConfigurationError(f"Stage YAML 必须是文件: {selected}")
    try:
        payload: Any = yaml.safe_load(selected.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, yaml.YAMLError) as error:
        raise ConfigurationError(f"Stage YAML 无法读取: {selected}") from error
    if not isinstance(payload, dict):
        raise ConfigurationError("Stage YAML 顶层必须是 mapping")
    return STAGE_MODELS[step].model_validate(payload)


def compose_config(
    step: int,
    project_root: Path,
    *,
    fragment: BaseModel,
    run_root: Path | None,
) -> EasyDesignRunConfig:
    if step == 1:
        root = resolve_project_path(project_root, must_exist=True)
        current = load_run_config(
            project_config_path(root), source_base_dir=root
        ).config
    else:
        if run_root is None:
            raise ConfigurationError(f"Stage {step:02d} 需要同一项目的上游 run")
        resolved, _ = load_resolved_run_config(run_root)
        current = resolved.user_config
    payload = current.model_dump(mode="python", exclude_none=False)
    payload[f"stage{step:02d}"] = fragment.model_dump(mode="python", exclude_none=False)
    workflow = payload["workflow"]
    if not isinstance(workflow, dict):
        raise ConfigurationError("canonical workflow 不是 mapping")
    workflow["execution_mode"] = "review-gated"
    workflow["stop_after_stage"] = step
    for future in range(step + 1, 8):
        payload[f"stage{future:02d}"] = None
    return EasyDesignRunConfig.model_validate(payload)


def validate_composed_config(project_root: Path, config: EasyDesignRunConfig) -> None:
    context = WorkspaceContext.discover()
    staging = context.runtime_root / "tmp" / f"step-config-{uuid4().hex}.yaml"
    context.require_write_path(staging, purpose="Stage 配置验证")
    staging.parent.mkdir(parents=True, exist_ok=True)
    try:
        with staging.open("x", encoding="utf-8", newline="\n") as handle:
            yaml.safe_dump(
                config.model_dump(mode="json", exclude_none=False),
                handle,
                allow_unicode=True,
                sort_keys=False,
            )
        load_run_config(
            staging,
            source_base_dir=resolve_project_path(project_root, must_exist=True),
        )
    finally:
        if staging.is_file():
            staging.unlink()


def initialize_local_project(
    *,
    project_root: Path,
    target: Path | None = None,
    target_bundle: Path | None = None,
    source_run_root: Path | None = None,
    pdb_id: str | None = None,
    uniprot: str | None = None,
    uniprot_query: str | None = None,
    taxon_id: int | None = None,
    chain: str | None = None,
    chain_namespace: str = "auth",
    identity_uniprot: str | None = None,
    project_id: str | None = None,
    target_id: str | None = None,
    scope_range: tuple[int, int] | None = None,
    scope_feature_type: str | None = None,
    scope_feature_name: str | None = None,
    precomputed_msa: Path | None = None,
    msa_cache_mode: str = "online",
) -> InitializedProject:
    root = resolve_project_path(project_root, must_exist=False)
    if source_run_root is not None:
        context = WorkspaceContext.discover()
        source_root = source_run_root.expanduser().resolve(strict=True)
        example_root = (context.root / "examples/apoe-ui-demo").resolve(strict=False)
        if not (
            source_root.is_relative_to(context.runs_root)
            or source_root.is_relative_to(example_root)
        ):
            raise ConfigurationError(
                "拒绝读取或继续外部/旧 UI run；只允许当前 local run 或 Git APOE evidence"
            )
    initialized = initialize_project(
        project_root=root,
        target=target,
        target_bundle=target_bundle,
        source_run_root=source_run_root,
        pdb_id=pdb_id,
        uniprot=uniprot,
        uniprot_query=uniprot_query,
        taxon_id=taxon_id,
        chain=chain,
        chain_namespace=chain_namespace,
        identity_uniprot=identity_uniprot,
        project_id=project_id,
        target_id=target_id,
        stop_after_stage=7,
        stage02_method="both",
        execution_mode="review-gated",
        scope_range=scope_range,
        scope_feature_type=scope_feature_type,
        scope_feature_name=scope_feature_name,
        precomputed_msa=precomputed_msa,
        msa_cache_mode=msa_cache_mode,
    )
    try:
        raw: Any = yaml.safe_load(initialized.config_path.read_text(encoding="utf-8"))
        full = EasyDesignRunConfig.model_validate(raw)
        for step, filename in STAGE_FILENAMES.items():
            stage = getattr(full, f"stage{step:02d}")
            if stage is None:
                raise ConfigurationError(f"初始化默认配置缺少 Stage {step:02d}")
            if step == 2:
                # The full UI used PSE source colors as an implicit manual
                # proposal. The local product defaults to independent SASA
                # and ScanNet; manual regions require an explicit Stage YAML.
                stage_payload = stage.model_dump(mode="python", exclude_none=False)
                stage_payload["mode"] = "automatic"
                stage_payload["user_regions"] = None
                stage = Stage02Config.model_validate(stage_payload)
            with (root / filename).open("x", encoding="utf-8", newline="\n") as handle:
                yaml.safe_dump(
                    stage.model_dump(mode="json", exclude_none=False),
                    handle,
                    allow_unicode=True,
                    sort_keys=False,
                )
        initial_payload = full.model_dump(mode="python", exclude_none=False)
        initial_payload["workflow"]["stop_after_stage"] = 1
        for step in range(2, 8):
            initial_payload[f"stage{step:02d}"] = None
        initial = EasyDesignRunConfig.model_validate(initial_payload)
        initialized.config_path.unlink()
        gitignore = root / ".gitignore"
        if gitignore.is_file():
            gitignore.unlink()
        revision = publish_config_revision(root, initial)
    except Exception:
        # initialize_project already owns quarantine semantics.  Never remove
        # an existing user project here; this block only handles its fresh tree.
        raise
    return InitializedProject(
        project_root=root,
        config_path=revision,
        target_path=initialized.target_path,
        msa_path=initialized.msa_path,
        detected_format=initialized.detected_format,
    )


def _binding_path(context: WorkspaceContext, project_id: str) -> Path:
    return context.runtime_root / "state/local-projects" / f"{project_id}.json"


def bind_project_run(project_root: Path, run_root: Path) -> LocalProjectRunBinding:
    context = WorkspaceContext.discover()
    root = resolve_project_path(project_root, must_exist=True)
    manifest_name = read_last_text_line(run_root / "manifests/LATEST")
    manifest = load_model(run_root / "manifests" / manifest_name, RunManifest)
    binding = LocalProjectRunBinding(
        project_id=manifest.project_id,
        project_root=root,
        run_id=manifest.run_id,
        run_root=run_root.resolve(),
        updated_at=datetime.now(UTC),
    )
    atomic_dump_runtime_model(binding, _binding_path(context, manifest.project_id))
    return binding


def resolve_project_run(
    project_root: Path,
    *,
    run_id: str | None = None,
    required: bool = True,
) -> RunSummary | None:
    context = WorkspaceContext.discover()
    root = resolve_project_path(project_root, must_exist=True)
    project_id = load_run_config(
        project_config_path(root), source_base_dir=root
    ).config.project_id
    summaries = [
        item
        for item in list_runs(context.runs_root)
        if item.project_id == project_id and (run_id is None or item.run_id == run_id)
    ]
    if run_id is None:
        binding_path = _binding_path(context, project_id)
        if binding_path.is_file():
            binding = load_latest_runtime_model(binding_path, LocalProjectRunBinding)
            summaries = [item for item in summaries if item.run_id == binding.run_id]
    if len(summaries) == 1:
        return summaries[0]
    if not summaries and not required:
        return None
    if not summaries:
        raise ConfigurationError(f"项目没有匹配 run: project={project_id}, run={run_id}")
    raise ConfigurationError("项目存在多个 run；请显式提供 --run RUN_ID")


def completed_steps(run_root: Path) -> tuple[int, ...]:
    name = read_last_text_line(run_root / "manifests/LATEST")
    run = load_model(run_root / "manifests" / name, RunManifest)
    values: list[int] = []
    for reference in run.stage_manifest_refs:
        stage = load_model(reference.verify(run_root), StageManifest)
        if stage.status is ExecutionStatus.SUCCEEDED and reference.producer_stage:
            values.append(int(reference.producer_stage.split("-", maxsplit=1)[0]))
    return tuple(sorted(values))


def completed_config_matches(run_root: Path, step: int, fragment: BaseModel) -> bool:
    resolved, _ = load_resolved_run_config(run_root)
    frozen = getattr(resolved.user_config, f"stage{step:02d}")
    return bool(frozen == fragment)


__all__ = [
    "LocalProjectRunBinding",
    "STAGE_FILENAMES",
    "bind_project_run",
    "completed_config_matches",
    "completed_steps",
    "compose_config",
    "initialize_local_project",
    "project_config_path",
    "publish_config_revision",
    "read_stage_fragment",
    "resolve_project_path",
    "resolve_project_run",
    "validate_composed_config",
]
