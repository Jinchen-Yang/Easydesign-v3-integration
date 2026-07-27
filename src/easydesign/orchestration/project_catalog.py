"""可恢复项目归档；科学 artifact 与 manifest 保持字节不变。"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from easydesign.core import (
    ConfigurationError,
    ManifestStateError,
    RunManifest,
    StageManifest,
    load_model,
    sha256_file,
)

from .workspace import (
    RunIndex,
    RunIndexEntry,
    replace_run_index_entries,
)

PROJECT_RUN = "project-run"
ARCHIVED_PROJECT_RUN = "archived-project-run"
DEVELOPER_SMOKE_RUN = "developer-smoke-run"
TERMINAL_RUN_STATUSES = {"succeeded", "failed"}
PAUSED_INDEX_STATUSES = {
    "awaiting-human-approval",
    "awaiting-region-selection",
    "stage02-blocked",
}
LEGACY_TERMINAL_INDEX_STATUSES = {
    "stage01-succeeded",
    "succeeded",
    "failed",
}


@dataclass(frozen=True, slots=True)
class ProjectCatalogEntry:
    project_id: str
    category: str
    run_count: int
    paths: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ProjectArchiveOutcome:
    project_id: str
    category: str
    moved_paths: tuple[tuple[str, str], ...]
    index_path: Path


@dataclass(frozen=True, slots=True)
class ProjectPrimaryRunOutcome:
    project_id: str
    run_id: str
    path: str
    index_path: Path


def _load_index(runs_root: Path) -> RunIndex:
    index_path = runs_root.resolve() / "run-index.json"
    if not index_path.is_file():
        raise ConfigurationError(f"运行索引不存在: {index_path}")
    return load_model(index_path, RunIndex)


def list_project_catalog(
    runs_root: Path,
    *,
    include_archived: bool = False,
    include_developer_smoke: bool = False,
) -> tuple[ProjectCatalogEntry, ...]:
    """只读取运行索引生成项目目录，不扫描运行目录。"""

    allowed = {PROJECT_RUN}
    if include_archived:
        allowed.add(ARCHIVED_PROJECT_RUN)
    if include_developer_smoke:
        allowed.add(DEVELOPER_SMOKE_RUN)
    grouped: dict[tuple[str, str], list[str]] = {}
    for entry in _load_index(runs_root).entries:
        if entry.category not in allowed or entry.project_id is None:
            continue
        grouped.setdefault((entry.project_id, entry.category), []).append(entry.path)
    return tuple(
        ProjectCatalogEntry(
            project_id=project_id,
            category=category,
            run_count=len(paths),
            paths=tuple(sorted(paths)),
        )
        for (project_id, category), paths in sorted(grouped.items())
    )


def select_project_primary_run(
    runs_root: Path,
    *,
    project_id: str,
    run_id: str,
    changed_at: datetime | None = None,
) -> ProjectPrimaryRunOutcome:
    """选择项目首页展示的运行；不改变运行或科学产物。"""

    root = runs_root.resolve()
    index = _load_index(root)
    matches = [
        entry
        for entry in index.entries
        if entry.category == PROJECT_RUN
        and entry.project_id == project_id
        and entry.run_id == run_id
    ]
    if not matches:
        raise ConfigurationError(
            f"项目 {project_id} 没有可作为主展示运行的 run_id={run_id}"
        )
    if len(matches) != 1:
        raise ManifestStateError(
            f"项目 {project_id} 的 run_id={run_id} 在索引中不唯一"
        )
    selected = matches[0]
    _verify_run_at_path(root, selected.path)
    updated = tuple(
        entry.model_copy(
            update={
                "is_project_primary": (
                    entry.category == PROJECT_RUN
                    and entry.project_id == project_id
                    and entry.run_id == run_id
                )
            }
        )
        if entry.category == PROJECT_RUN and entry.project_id == project_id
        else entry
        for entry in index.entries
    )
    index_path = replace_run_index_entries(
        root,
        updated,
        generated_at=changed_at or datetime.now(UTC),
    )
    return ProjectPrimaryRunOutcome(
        project_id=project_id,
        run_id=run_id,
        path=selected.path,
        index_path=index_path,
    )


def _assert_movable(root: Path, entry: RunIndexEntry) -> None:
    if entry.run_id is None or entry.project_id is None:
        raise ManifestStateError(f"项目运行索引缺少 project_id/run_id: {entry.path}")
    source = (root / entry.path).resolve()
    if not source.is_relative_to(root) or not source.is_dir():
        raise ManifestStateError(f"运行路径不在 runs_root 或不存在: {entry.path}")
    if entry.layout_version == "legacy-0":
        if entry.status not in LEGACY_TERMINAL_INDEX_STATUSES:
            raise ManifestStateError(
                f"旧版运行 {entry.path} 状态为 {entry.status}，不能归档或恢复"
            )
        _legacy_layout_fingerprint(root, entry.path)
        if any(source.rglob("*.lock")):
            raise ManifestStateError(f"运行目录仍存在锁文件，拒绝移动: {entry.path}")
        return
    run = _verify_run_at_path(root, entry.path)
    run_status = str(run.status)
    if (
        run_status not in TERMINAL_RUN_STATUSES
        and entry.status not in PAUSED_INDEX_STATUSES
    ):
        raise ManifestStateError(
            f"运行 {entry.path} 状态为 {run.status}，未终态运行不能归档或恢复"
        )
    if any(source.rglob("*.lock")):
        raise ManifestStateError(f"运行目录仍存在锁文件，拒绝移动: {entry.path}")


def _legacy_layout_fingerprint(
    root: Path,
    relative_path: str,
) -> tuple[tuple[str, str, int, str], ...]:
    """为无 manifest 的只读历史目录建立可重复字节清单。"""

    run_root = (root / relative_path).resolve()
    if not run_root.is_relative_to(root) or not run_root.is_dir():
        raise ManifestStateError(f"旧版运行路径不存在或逃逸 runs_root: {relative_path}")
    inventory: list[tuple[str, str, int, str]] = []
    for path in sorted(run_root.rglob("*")):
        if path.is_symlink():
            raise ManifestStateError(f"旧版运行含符号链接，拒绝移动: {path}")
        relative = path.relative_to(run_root).as_posix()
        if path.is_dir():
            inventory.append((relative, "directory", 0, ""))
        elif path.is_file():
            inventory.append((relative, "file", path.stat().st_size, sha256_file(path)))
        else:
            raise ManifestStateError(f"旧版运行含不支持的目录项: {path}")
    return tuple(inventory)


def _verify_run_at_path(root: Path, relative_path: str) -> RunManifest:
    run_root = (root / relative_path).resolve()
    if not run_root.is_relative_to(root) or not run_root.is_dir():
        raise ManifestStateError(f"运行路径不在 runs_root 或不存在: {relative_path}")
    pointer = run_root / "manifests" / "LATEST"
    try:
        latest = pointer.read_text(encoding="utf-8").strip()
    except OSError as error:
        raise ManifestStateError(f"无法读取运行 LATEST: {relative_path}") from error
    run = load_model(run_root / "manifests" / latest, RunManifest)
    run.config_snapshot.verify(run_root)
    for stage_reference in run.stage_manifest_refs:
        stage = load_model(stage_reference.verify(run_root), StageManifest)
        # 归档是目录治理，不是科学成功门。失败、暂停和科学停止的 Stage
        # 同样是必须保留的审计证据；这里验证声明闭包而不篡改其状态。
        for artifact in stage.input_artifacts + stage.output_artifacts:
            artifact.verify(run_root)
    return run


def _move_project(
    runs_root: Path,
    *,
    project_id: str,
    source_category: str,
    destination_category: str,
    archive: bool,
    changed_at: datetime | None,
) -> ProjectArchiveOutcome:
    root = runs_root.resolve()
    index = _load_index(root)
    selected = tuple(
        entry
        for entry in index.entries
        if entry.project_id == project_id and entry.category == source_category
    )
    if not selected:
        raise ConfigurationError(
            f"项目 {project_id} 没有 category={source_category} 的运行"
        )
    for entry in selected:
        _assert_movable(root, entry)
    legacy_fingerprints = {
        entry.path: _legacy_layout_fingerprint(root, entry.path)
        for entry in selected
        if entry.layout_version == "legacy-0"
    }

    replacements: dict[str, RunIndexEntry] = {}
    moves: list[tuple[Path, Path]] = []
    for entry in selected:
        assert entry.run_id is not None
        source = (root / entry.path).resolve()
        relative = (
            Path("_archive") / project_id / entry.run_id
            if archive
            else Path(project_id) / entry.run_id
        )
        destination = (root / relative).resolve()
        if not destination.is_relative_to(root):
            raise ManifestStateError(f"目标路径逃逸 runs_root: {relative}")
        if destination.exists():
            raise ManifestStateError(f"目标运行目录已存在，拒绝覆盖: {destination}")
        replacements[entry.path] = entry.model_copy(
            update={
                "category": destination_category,
                "path": relative.as_posix(),
                "is_project_primary": False,
                "notes": entry.notes
                + (
                    (
                        "Archived without changing scientific artifacts."
                        if archive
                        else "Restored from recoverable archive."
                    ),
                ),
            }
        )
        moves.append((source, destination))

    completed: list[tuple[Path, Path]] = []
    index_replaced = False
    try:
        for source, destination in moves:
            destination.parent.mkdir(parents=True, exist_ok=True)
            os.replace(source, destination)
            completed.append((source, destination))
        for source_entry in selected:
            replacement = replacements[source_entry.path]
            if source_entry.layout_version == "legacy-0":
                if (
                    _legacy_layout_fingerprint(root, replacement.path)
                    != legacy_fingerprints[source_entry.path]
                ):
                    raise ManifestStateError(
                        f"旧版运行移动后字节清单改变: {replacement.path}"
                    )
            else:
                _verify_run_at_path(root, replacement.path)
        updated = tuple(
            replacements.get(entry.path, entry)
            for entry in index.entries
            if entry.path not in replacements
        ) + tuple(replacements.values())
        timestamp = changed_at or datetime.now(UTC)
        index_path = replace_run_index_entries(
            root,
            updated,
            generated_at=timestamp,
        )
        index_replaced = True
    except Exception:
        for source, destination in reversed(completed):
            if destination.exists() and not source.exists():
                source.parent.mkdir(parents=True, exist_ok=True)
                os.replace(destination, source)
        if index_replaced:
            replace_run_index_entries(
                root,
                index.entries,
                generated_at=index.generated_at,
            )
        raise

    return ProjectArchiveOutcome(
        project_id=project_id,
        category=destination_category,
        moved_paths=tuple(
            (source.relative_to(root).as_posix(), destination.relative_to(root).as_posix())
            for source, destination in moves
        ),
        index_path=index_path,
    )


def archive_project(
    runs_root: Path,
    project_id: str,
    *,
    changed_at: datetime | None = None,
) -> ProjectArchiveOutcome:
    return _move_project(
        runs_root,
        project_id=project_id,
        source_category=PROJECT_RUN,
        destination_category=ARCHIVED_PROJECT_RUN,
        archive=True,
        changed_at=changed_at,
    )


def restore_project(
    runs_root: Path,
    project_id: str,
    *,
    changed_at: datetime | None = None,
) -> ProjectArchiveOutcome:
    return _move_project(
        runs_root,
        project_id=project_id,
        source_category=ARCHIVED_PROJECT_RUN,
        destination_category=PROJECT_RUN,
        archive=False,
        changed_at=changed_at,
    )
