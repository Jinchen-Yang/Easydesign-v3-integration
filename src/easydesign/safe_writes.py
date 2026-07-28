"""Non-destructive helpers for failed workspace-local staging paths."""

from __future__ import annotations

import os
from pathlib import Path

from .workspace_context import WorkspaceContext


def read_last_text_line(path: Path) -> str:
    """Read the latest immutable pointer revision, with legacy append support."""

    revision_root = path.with_name(f"{path.name}.revisions")
    revisions = sorted(revision_root.glob("revision-*.txt"))
    selected = revisions[-1] if revisions else path
    lines = [line.strip() for line in selected.read_text(encoding="utf-8").splitlines()]
    values = [line for line in lines if line]
    if not values:
        raise OSError(f"Pointer 没有有效 revision: {selected}")
    return values[-1]


def append_pointer_revision(path: Path, value: str) -> Path:
    """Publish a pointer without changing any previously published bytes."""

    normalized = value.strip()
    if not normalized or "\n" in normalized or "\r" in normalized:
        raise ValueError("Pointer revision 必须是单行非空文本")
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        destination = path
    else:
        revision_root = path.with_name(f"{path.name}.revisions")
        revision_root.mkdir(parents=True, exist_ok=True)
        revisions = sorted(revision_root.glob("revision-*.txt"))
        next_revision = 1
        if revisions:
            try:
                next_revision = int(revisions[-1].stem.split("-")[-1]) + 1
            except ValueError as error:
                raise OSError(
                    f"Pointer revision 文件名损坏: {revisions[-1]}"
                ) from error
        destination = revision_root / f"revision-{next_revision:06d}.txt"
    with destination.open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(normalized + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    return destination


def quarantine_if_workspace_path(
    path: Path | None,
    *,
    operation: str,
    reason: str,
) -> Path | None:
    """Move an existing workspace path to quarantine; preserve external paths."""

    if path is None or not path.exists():
        return None
    try:
        context = WorkspaceContext.discover(path)
        context.assert_write_path(path)
    except Exception:
        return None
    return context.quarantine(path, operation=operation, reason=reason)
