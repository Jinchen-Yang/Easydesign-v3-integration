"""Flat project files and append-only canonical configuration revisions."""

from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path

import yaml  # type: ignore[import-untyped]
from pydantic import BaseModel, ConfigDict

from easydesign.core import (
    ConfigurationError,
    ExecutionStatus,
    ManifestStateError,
    RunManifest,
    StageManifest,
    load_model,
)
from easydesign.safe_writes import read_last_text_line
from easydesign.workspace_context import WorkspaceContext

from .application import RunSummary, list_runs, show_run
from .config import EasyDesignRunConfig, load_run_config
from .task_tracking import atomic_dump_runtime_model, load_latest_runtime_model

STAGE_FILENAMES = {
    1: "01-target-preparation.yaml",
    2: "02-hotspot-discovery.yaml",
    3: "03-boltzgen-configuration.yaml",
    4: "04-pilot-generation.yaml",
    5: "05-pilot-filtering.yaml",
    6: "06-scale-generation-and-refolding.yaml",
    7: "07-final-filtering-and-selection.yaml",
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
        raise ConfigurationError("本地产品只接受当前 workspace/projects；拒绝旧 UI 或外部项目路径")
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
    project_id = load_run_config(project_config_path(root), source_base_dir=root).config.project_id

    # The project binding is the current-run authority and already identifies one
    # indexed run.  Resolve that run directly instead of listing and integrity-
    # checking every historical run in the workspace on each agent state read.
    # The fallback below is retained for old projects that predate local bindings.
    if run_id is None:
        binding_path = _binding_path(context, project_id)
        if binding_path.is_file():
            binding = load_latest_runtime_model(binding_path, LocalProjectRunBinding)
            if binding.project_id != project_id:
                raise ConfigurationError("本地项目 run binding 与当前项目身份不一致")
            try:
                selector = (
                    binding.run_root.resolve().relative_to(context.runs_root.resolve()).as_posix()
                )
            except ValueError as error:
                raise ConfigurationError("本地项目 run binding 逃出 workspace/runs") from error
            summary = show_run(context.runs_root, selector)
            if (
                summary.project_id != project_id
                or summary.run_id != binding.run_id
                or summary.path.resolve() != binding.run_root.resolve()
            ):
                raise ConfigurationError("本地项目 run binding 与 run-index 不一致")
            return summary

    if run_id is not None:
        # A run id is scoped to its project. Concurrent projects may start in the
        # same second and legitimately share the timestamp-based id, so resolve the
        # indexed project/run path instead of the workspace-wide bare id.
        selector = f"{project_id}/{run_id}"
        try:
            summary = show_run(context.runs_root, selector)
        except ManifestStateError as error:
            # Preserve the public project API's historical "no matching run"
            # contract while allowing genuine manifest-integrity failures to
            # retain their more specific error type.
            missing = "run-index 没有匹配 run" in str(error) or "run-index 不存在" in str(error)
            if not missing:
                raise
            if not required:
                return None
            raise ConfigurationError(
                f"项目没有匹配 run: project={project_id}, run={run_id}"
            ) from error
        if summary.project_id == project_id:
            return summary
        if not required:
            return None
        raise ConfigurationError(f"项目没有匹配 run: project={project_id}, run={run_id}")

    summaries = [item for item in list_runs(context.runs_root) if item.project_id == project_id]
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


__all__ = [
    "LocalProjectRunBinding",
    "STAGE_FILENAMES",
    "bind_project_run",
    "completed_steps",
    "project_config_path",
    "publish_config_revision",
    "resolve_project_path",
    "resolve_project_run",
]
