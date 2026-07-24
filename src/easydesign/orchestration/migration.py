"""不修改历史产物内容的 run 目录整体迁移。"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from easydesign.core import (
    ArtifactIntegrityError,
    ManifestStateError,
    dump_model,
    load_model,
    sha256_file,
    verify_sha256,
)
from easydesign.core.artifacts import SHA256_PATTERN, resolve_run_relative_path
from easydesign.core.timestamps import normalize_aware_datetime

from .workspace import RunIndexEntry, upsert_run_index_entries


def _validate_relative(value: str) -> str:
    path = PurePosixPath(value)
    if path.is_absolute() or not value or str(path) != value:
        raise ValueError("迁移路径必须是规范 POSIX 相对路径")
    if any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError("迁移路径不能包含空段、'.' 或 '..'")
    return value


class RunMovePlan(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    source: str
    destination: str
    classification: str = Field(min_length=1, max_length=64)

    @field_validator("source", "destination")
    @classmethod
    def validate_path(cls, value: str) -> str:
        return _validate_relative(value)


class TreeFingerprint(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    sha256: str = Field(pattern=SHA256_PATTERN)
    file_count: int = Field(ge=0)
    size_bytes: int = Field(ge=0)


class CompletedRunMove(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    source: str
    destination: str
    classification: str
    fingerprint: TreeFingerprint


class RunMigrationManifest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: str = "0.1"
    migration_id: str = Field(min_length=1, max_length=128)
    moved_at: datetime
    moves: tuple[CompletedRunMove, ...]

    @field_validator("moved_at")
    @classmethod
    def normalize_datetime(cls, value: datetime) -> datetime:
        return normalize_aware_datetime(value)

    @model_validator(mode="after")
    def validate_unique_paths(self) -> Self:
        sources = [move.source for move in self.moves]
        destinations = [move.destination for move in self.moves]
        if len(sources) != len(set(sources)) or len(destinations) != len(set(destinations)):
            raise ValueError("迁移 source/destination 不能重复")
        return self


def fingerprint_tree(root: Path) -> TreeFingerprint:
    """对目录内相对路径、大小和文件内容建立稳定 fingerprint。"""

    if not root.is_dir():
        raise ManifestStateError(f"待 fingerprint 的目录不存在: {root}")
    digest = hashlib.sha256()
    file_count = 0
    total_size = 0
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise ManifestStateError(f"历史 run 含 symlink，拒绝自动迁移: {path}")
        if not path.is_file():
            continue
        relative = path.relative_to(root).as_posix()
        size = path.stat().st_size
        content_sha256 = sha256_file(path)
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(str(size).encode("ascii"))
        digest.update(b"\0")
        digest.update(content_sha256.encode("ascii"))
        digest.update(b"\n")
        file_count += 1
        total_size += size
    return TreeFingerprint(
        sha256=digest.hexdigest(),
        file_count=file_count,
        size_bytes=total_size,
    )


def _iter_artifact_like(value: Any) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    if isinstance(value, dict):
        if {"relative_path", "sha256", "size_bytes"} <= value.keys():
            found.append(value)
        for child in value.values():
            found.extend(_iter_artifact_like(child))
    elif isinstance(value, list):
        for child in value:
            found.extend(_iter_artifact_like(child))
    return found


def _validate_json_artifact_refs(run_root: Path) -> None:
    candidates = tuple(run_root.rglob("*manifest*.json")) + tuple(
        run_root.rglob("target-bundle.json")
    )
    for path in candidates:
        try:
            raw: Any = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise ManifestStateError(f"历史 JSON 无法审计: {path}") from error
        for reference in _iter_artifact_like(raw):
            relative_path = reference["relative_path"]
            expected_sha256 = reference["sha256"]
            expected_size = reference["size_bytes"]
            if not isinstance(relative_path, str) or relative_path.startswith("/"):
                raise ManifestStateError(f"历史 artifact 不是 run 相对路径: {path}")
            artifact_path = resolve_run_relative_path(run_root, relative_path)
            if not artifact_path.is_file():
                raise ArtifactIntegrityError(f"历史 artifact 缺失: {artifact_path}")
            if artifact_path.stat().st_size != expected_size:
                raise ArtifactIntegrityError(f"历史 artifact 大小不一致: {artifact_path}")
            verify_sha256(artifact_path, expected_sha256)


def _remove_empty_source_parents(runs_root: Path, source: Path) -> None:
    candidate = source.parent
    while candidate != runs_root and runs_root in candidate.parents:
        try:
            candidate.rmdir()
        except OSError:
            break
        candidate = candidate.parent


def migrate_run_directories(
    *,
    runs_root: Path,
    migration_relative_path: str,
    migration_id: str,
    moved_at: datetime,
    plans: tuple[RunMovePlan, ...],
    index_entries: tuple[RunIndexEntry, ...],
) -> RunMigrationManifest:
    """整体移动目录、验证内容未变，并写入不可覆盖的迁移清单。"""

    root = runs_root.resolve()
    root.mkdir(parents=True, exist_ok=True)
    manifest_path = root / _validate_relative(migration_relative_path)
    if manifest_path.is_file():
        existing = load_model(manifest_path, RunMigrationManifest)
        for move in existing.moves:
            destination = root / move.destination
            if fingerprint_tree(destination) != move.fingerprint:
                raise ArtifactIntegrityError(f"已迁移 run fingerprint 改变: {destination}")
            _validate_json_artifact_refs(destination)
        upsert_run_index_entries(root, index_entries, generated_at=moved_at)
        return existing

    completed: list[CompletedRunMove] = []
    for plan in plans:
        source = root / plan.source
        destination = root / plan.destination
        if source.exists() == destination.exists():
            raise ManifestStateError(
                "迁移要求 source/destination 恰好存在一个: "
                f"source={source.exists()}, destination={destination.exists()}, "
                f"plan={plan.source}->{plan.destination}"
            )
        before = fingerprint_tree(source if source.exists() else destination)
        if source.exists():
            _validate_json_artifact_refs(source)
            destination.parent.mkdir(parents=True, exist_ok=True)
            source.rename(destination)
            _remove_empty_source_parents(root, source)
        after = fingerprint_tree(destination)
        if before != after:
            raise ArtifactIntegrityError(
                f"目录迁移前后 fingerprint 不一致: {plan.source}->{plan.destination}"
            )
        _validate_json_artifact_refs(destination)
        completed.append(
            CompletedRunMove(
                source=plan.source,
                destination=plan.destination,
                classification=plan.classification,
                fingerprint=after,
            )
        )

    manifest = RunMigrationManifest(
        migration_id=migration_id,
        moved_at=moved_at,
        moves=tuple(completed),
    )
    dump_model(manifest, manifest_path)
    upsert_run_index_entries(root, index_entries, generated_at=moved_at)
    return manifest
