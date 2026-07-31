"""Portable UI path references plus current-machine path resolution.

Persistent UI state should not bake in deployment-specific ancestors such as
``/root/autodl-tmp``.  The helpers in this module keep records portable by
storing a logical reference, while still allowing diagnostic logs to include
the resolved absolute path for the current machine.
"""

from __future__ import annotations

from pathlib import Path

from easydesign.core import ConfigurationError, PathPolicyError
from easydesign.workspace_context import WorkspaceContext


def workspace_relative_path(workspace: WorkspaceContext, path: Path) -> str:
    """Return the legacy workspace-relative path for compatibility."""

    resolved = workspace.assert_write_path(path)
    return resolved.relative_to(workspace.root).as_posix()


def path_ref_for(workspace: WorkspaceContext, path: Path) -> str:
    """Return a portable logical reference for a workspace-local path."""

    resolved = workspace.assert_write_path(path)
    projects_root = workspace.projects_root
    runtime_root = workspace.runtime_root
    runs_root = workspace.runs_root
    archives_root = workspace.archives_root
    quarantine_root = runtime_root / "quarantine"

    if resolved == projects_root or resolved.is_relative_to(projects_root):
        relative = resolved.relative_to(projects_root)
        if not relative.parts:
            return "projects://"
        project_id = relative.parts[0]
        rest = Path(*relative.parts[1:]).as_posix() if len(relative.parts) > 1 else ""
        return f"project://{project_id}/{rest}" if rest else f"project://{project_id}"
    if resolved == quarantine_root or resolved.is_relative_to(quarantine_root):
        relative_text = resolved.relative_to(quarantine_root).as_posix()
        return f"quarantine://{relative_text}" if relative_text else "quarantine://"
    if resolved == runtime_root or resolved.is_relative_to(runtime_root):
        relative_text = resolved.relative_to(runtime_root).as_posix()
        return f"runtime://{relative_text}" if relative_text else "runtime://"
    if resolved == runs_root or resolved.is_relative_to(runs_root):
        relative_text = resolved.relative_to(runs_root).as_posix()
        return f"runs://{relative_text}" if relative_text else "runs://"
    if resolved == archives_root or resolved.is_relative_to(archives_root):
        relative_text = resolved.relative_to(archives_root).as_posix()
        return f"archives://{relative_text}" if relative_text else "archives://"
    if resolved == workspace.root or resolved.is_relative_to(workspace.root):
        relative_text = resolved.relative_to(workspace.root).as_posix()
        return f"workspace://{relative_text}" if relative_text else "workspace://"
    raise PathPolicyError(f"无法为工作区外路径生成引用: {resolved}")


def resolve_path_ref(workspace: WorkspaceContext, reference: str) -> Path:
    """Resolve a portable logical reference on the current machine."""

    if reference == "runtime://":
        return workspace.runtime_root
    if reference.startswith("runtime://"):
        return workspace.assert_write_path(
            workspace.runtime_root / reference.removeprefix("runtime://")
        )
    if reference == "quarantine://":
        return workspace.runtime_root / "quarantine"
    if reference.startswith("quarantine://"):
        return workspace.assert_write_path(
            workspace.runtime_root
            / "quarantine"
            / reference.removeprefix("quarantine://")
        )
    if reference == "projects://":
        return workspace.projects_root
    if reference.startswith("project://"):
        relative = reference.removeprefix("project://")
        if not relative or ".." in Path(relative).parts:
            raise ConfigurationError(f"无效项目路径引用: {reference}")
        return workspace.assert_write_path(workspace.projects_root / relative)
    if reference == "runs://":
        return workspace.runs_root
    if reference.startswith("runs://"):
        return workspace.assert_write_path(
            workspace.runs_root / reference.removeprefix("runs://")
        )
    if reference == "archives://":
        return workspace.archives_root
    if reference.startswith("archives://"):
        return workspace.assert_write_path(
            workspace.archives_root / reference.removeprefix("archives://")
        )
    if reference == "workspace://":
        return workspace.root
    if reference.startswith("workspace://"):
        relative = reference.removeprefix("workspace://")
        if ".." in Path(relative).parts:
            raise ConfigurationError(f"无效工作区路径引用: {reference}")
        return (workspace.root / relative).resolve(strict=False)
    raise ConfigurationError(f"不支持的路径引用: {reference}")
