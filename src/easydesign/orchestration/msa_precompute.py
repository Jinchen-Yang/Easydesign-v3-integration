"""Resolve, validate, register, and snapshot precomputed MSA artifacts.

Bulk Stockholm conversion and release production are maintainer concerns.  This
module only consumes already-built libraries or one explicit A3M file.
"""

from __future__ import annotations

import ctypes
import hashlib
import json
import os
import re
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from easydesign.core import (
    ConfigurationError,
    EasyDesignError,
    MsaLibraryEntry,
    MsaLibraryManifest,
    MsaReleaseReceipt,
    MsaSourceReceipt,
    dump_model,
    load_model,
    sha256_file,
)
from easydesign.core.artifacts import ID_PATTERN
from easydesign.workspace_context import WorkspaceContext

NEW_LIBRARY_SCHEMA_VERSION = "1.0"
LEGACY_LIBRARY_SCHEMA_VERSION = "0.2"


class MsaArtifactError(ConfigurationError):
    """An A3M or library failed its immutable input contract."""


def _publish_directory_no_replace(source: Path, destination: Path) -> None:
    """Atomically publish a completed directory without replacing a target."""

    if destination.exists():
        raise FileExistsError(destination)
    if os.name == "nt":
        os.rename(source, destination)
        return
    try:
        libc = ctypes.CDLL(None, use_errno=True)
        renameat2 = libc.renameat2
    except (AttributeError, OSError) as error:
        raise MsaArtifactError(
            "当前平台不支持安全的目录 no-replace 发布"
        ) from error
    renameat2.argtypes = [
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_uint,
    ]
    renameat2.restype = ctypes.c_int
    result = renameat2(
        -100,
        os.fsencode(source),
        -100,
        os.fsencode(destination),
        1,  # renameat2(2): RENAME_NOREPLACE
    )
    if result == 0:
        return
    error_number = ctypes.get_errno()
    if error_number == 17:
        raise FileExistsError(destination)
    raise MsaArtifactError(
        "MSA directory staging 无法原子发布: "
        f"{source} -> {destination} (errno={error_number})"
    )


@dataclass(frozen=True, slots=True)
class ValidatedMsaArtifact:
    source_path: Path
    receipt: MsaSourceReceipt


@dataclass(frozen=True, slots=True)
class MsaInputSnapshot:
    root: Path
    a3m_path: Path
    receipt_path: Path
    receipt: MsaSourceReceipt


@dataclass(frozen=True, slots=True)
class _LibraryRelease:
    root: Path
    manifest_path: Path
    manifest_sha256: str
    schema_version: str
    release_id: str
    entries: tuple[MsaLibraryEntry | dict[str, Any], ...]
    release_receipt_path: Path | None
    release_receipt_sha256: str | None


def _require_release_id(release_id: str) -> str:
    if re.fullmatch(ID_PATTERN, release_id) is None:
        raise MsaArtifactError(f"MSA library release ID 不合法: {release_id!r}")
    return release_id


def _read_json(path: Path, *, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise MsaArtifactError(f"{label} 无法读取: {path}") from error
    if not isinstance(payload, dict):
        raise MsaArtifactError(f"{label} 顶层必须是 JSON object")
    return payload


def validate_a3m(path: Path, *, expected_query: str) -> tuple[str, int, int]:
    """Stream-validate one A3M and require an exact, gap-free query row."""

    source = path.expanduser().resolve(strict=True)
    if not source.is_file():
        raise MsaArtifactError(f"A3M 必须是普通文件: {source}")
    record_count = 0
    query_parts: list[str] = []
    current_has_sequence = False
    try:
        with source.open("r", encoding="utf-8") as handle:
            for line_number, raw in enumerate(handle, start=1):
                line = raw.strip()
                if not line:
                    continue
                if line.startswith(">"):
                    if record_count and not current_has_sequence:
                        raise MsaArtifactError("A3M 包含空 sequence record")
                    record_count += 1
                    current_has_sequence = False
                    continue
                if record_count == 0:
                    raise MsaArtifactError(
                        f"A3M 在首个 header 前出现序列: line={line_number}"
                    )
                if not line.isascii() or any(
                    not (character.isalpha() or character in "-.*")
                    for character in line
                ):
                    raise MsaArtifactError(f"A3M 含非法字符: line={line_number}")
                if record_count == 1:
                    query_parts.append(line)
                current_has_sequence = True
    except (OSError, UnicodeDecodeError) as error:
        raise MsaArtifactError(f"A3M 无法作为 UTF-8 读取: {source}") from error
    if record_count and not current_has_sequence:
        raise MsaArtifactError("A3M 包含空 sequence record")
    if record_count < 2:
        raise MsaArtifactError(f"MSA depth 不足: depth={record_count}")
    query = "".join(query_parts)
    if query != expected_query:
        raise MsaArtifactError("A3M query 与 target canonical sequence 不一致")
    return sha256_file(source), source.stat().st_size, record_count


def _safe_library_entry(root: Path, relative: str) -> Path:
    candidate = Path(relative)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise MsaArtifactError("MSA library entry 路径不安全")
    try:
        source = (root / candidate).resolve(strict=True)
    except OSError as error:
        raise MsaArtifactError(f"MSA library A3M 不存在: {relative}") from error
    if not source.is_relative_to(root) or not source.is_file():
        raise MsaArtifactError("MSA library A3M 逃出 release root 或不是普通文件")
    return source


def _load_new_release(root: Path, *, release_id: str) -> _LibraryRelease:
    manifest_path = root / "library-manifest.json"
    receipt_path = root / "release-receipt.json"
    try:
        manifest = load_model(manifest_path, MsaLibraryManifest)
        receipt = load_model(receipt_path, MsaReleaseReceipt)
    except (EasyDesignError, OSError, ValidationError, ValueError) as error:
        raise MsaArtifactError(f"MSA library 1.0 contract 无效: {root}") from error
    manifest_sha256 = sha256_file(manifest_path)
    if manifest.release_id != release_id or receipt.release_id != release_id:
        raise MsaArtifactError("MSA library directory、manifest 与 receipt release ID 不一致")
    if receipt.library_manifest_sha256 != manifest_sha256:
        raise MsaArtifactError("MSA release receipt 未绑定当前 library manifest")
    if receipt.entry_count != len(manifest.entries):
        raise MsaArtifactError("MSA release receipt entry_count 与 manifest 不一致")
    return _LibraryRelease(
        root=root,
        manifest_path=manifest_path,
        manifest_sha256=manifest_sha256,
        schema_version=manifest.schema_version,
        release_id=release_id,
        entries=manifest.entries,
        release_receipt_path=receipt_path,
        release_receipt_sha256=sha256_file(receipt_path),
    )


def _load_legacy_release(root: Path, *, release_id: str) -> _LibraryRelease:
    manifest_path = root / "library-manifest.json"
    payload = _read_json(manifest_path, label="legacy MSA library manifest")
    if (
        payload.get("schema_version") != LEGACY_LIBRARY_SCHEMA_VERSION
        or payload.get("status") != "ready"
        or not isinstance(payload.get("entries"), list)
    ):
        raise MsaArtifactError("legacy MSA library manifest schema/status 不受支持")
    entries = tuple(item for item in payload["entries"] if isinstance(item, dict))
    if len(entries) != len(payload["entries"]) or not entries:
        raise MsaArtifactError("legacy MSA library entries 必须是非空 object 列表")
    return _LibraryRelease(
        root=root,
        manifest_path=manifest_path,
        manifest_sha256=sha256_file(manifest_path),
        schema_version=LEGACY_LIBRARY_SCHEMA_VERSION,
        release_id=release_id,
        entries=entries,
        release_receipt_path=None,
        release_receipt_sha256=None,
    )


def _load_release_root(root: Path, *, release_id: str) -> _LibraryRelease:
    resolved = root.expanduser().resolve(strict=True)
    if not resolved.is_dir() or resolved.name != release_id:
        raise MsaArtifactError("MSA library root 必须是以 release ID 命名的目录")
    manifest_path = resolved / "library-manifest.json"
    payload = _read_json(manifest_path, label="MSA library manifest")
    schema_version = payload.get("schema_version")
    if schema_version == NEW_LIBRARY_SCHEMA_VERSION:
        return _load_new_release(resolved, release_id=release_id)
    if schema_version == LEGACY_LIBRARY_SCHEMA_VERSION:
        return _load_legacy_release(resolved, release_id=release_id)
    raise MsaArtifactError(f"MSA library schema 不受支持: {schema_version!r}")


def _library_root(context: WorkspaceContext, release_id: str) -> Path:
    canonical = context.runtime_root / "databases" / "gpcr-msa" / release_id
    if canonical.is_dir():
        return canonical
    legacy = context.runtime_root / "databases" / release_id
    if legacy.is_dir():
        return legacy
    raise MsaArtifactError(
        "MSA library release 未注册到当前 clone: "
        f"release={release_id}, expected={canonical}"
    )


def _new_entry_for_sequence(
    release: _LibraryRelease,
    sequence_sha256: str,
) -> MsaLibraryEntry:
    matches = [
        item
        for item in release.entries
        if isinstance(item, MsaLibraryEntry)
        and item.canonical_sequence_sha256 == sequence_sha256
    ]
    if len(matches) != 1:
        raise MsaArtifactError(
            "MSA library 必须按 canonical sequence SHA-256 唯一匹配: "
            f"matches={len(matches)}"
        )
    return matches[0]


def _legacy_entry_for_sequence(
    release: _LibraryRelease,
    sequence_sha256: str,
) -> dict[str, Any]:
    matches = [
        item
        for item in release.entries
        if isinstance(item, dict)
        and item.get("status") == "converted"
        and (
            item.get("target_sequence_sha256")
            or item.get("query_sequence_sha256")
        )
        == sequence_sha256
    ]
    if len(matches) != 1:
        raise MsaArtifactError(
            "legacy MSA library 必须按 canonical sequence SHA-256 唯一匹配: "
            f"matches={len(matches)}"
        )
    return matches[0]


def resolve_library_entry(
    *,
    context: WorkspaceContext,
    release_id: str,
    canonical_sequence: str,
) -> ValidatedMsaArtifact:
    """Resolve one release entry by sequence content, never accession or filename."""

    selected_release = _require_release_id(release_id)
    sequence_sha256 = hashlib.sha256(canonical_sequence.encode("ascii")).hexdigest()
    release = _load_release_root(
        _library_root(context, selected_release),
        release_id=selected_release,
    )
    relative: str
    expected_a3m_sha256: str
    expected_size: int
    expected_depth: int
    if release.schema_version == NEW_LIBRARY_SCHEMA_VERSION:
        entry = _new_entry_for_sequence(release, sequence_sha256)
        relative = entry.a3m_path
        expected_a3m_sha256 = entry.a3m_sha256
        expected_size = entry.a3m_size_bytes
        expected_depth = entry.depth
    else:
        legacy_entry = _legacy_entry_for_sequence(release, sequence_sha256)
        legacy_relative = legacy_entry.get("a3m_path")
        legacy_a3m_sha256 = legacy_entry.get("a3m_sha256")
        legacy_size = legacy_entry.get("a3m_size_bytes")
        legacy_depth = legacy_entry.get("depth")
        if (
            not isinstance(legacy_relative, str)
            or not isinstance(legacy_a3m_sha256, str)
            or not isinstance(legacy_size, int)
            or not isinstance(legacy_depth, int)
        ):
            raise MsaArtifactError("legacy MSA library entry 缺少 A3M identity")
        relative = legacy_relative
        expected_a3m_sha256 = legacy_a3m_sha256
        expected_size = legacy_size
        expected_depth = legacy_depth
    source = _safe_library_entry(release.root, relative)
    actual_sha256, actual_size, actual_depth = validate_a3m(
        source,
        expected_query=canonical_sequence,
    )
    if (
        actual_sha256 != expected_a3m_sha256
        or actual_size != expected_size
        or actual_depth != expected_depth
    ):
        raise MsaArtifactError("MSA library entry 的 SHA-256、大小或 depth 不一致")
    receipt = MsaSourceReceipt(
        type="precomputed-library",
        release_id=release.release_id,
        library_schema_version=release.schema_version,
        library_manifest_sha256=release.manifest_sha256,
        release_receipt_sha256=release.release_receipt_sha256,
        library_entry_path=relative,
        canonical_sequence_sha256=sequence_sha256,
        a3m_sha256=actual_sha256,
        a3m_size_bytes=actual_size,
        depth=actual_depth,
    )
    return ValidatedMsaArtifact(source_path=source, receipt=receipt)


def resolve_explicit_a3m(
    *,
    source: Path,
    canonical_sequence: str,
) -> ValidatedMsaArtifact:
    """Validate one explicit file without pretending it belongs to a release."""

    resolved = source.expanduser().resolve(strict=True)
    actual_sha256, actual_size, actual_depth = validate_a3m(
        resolved,
        expected_query=canonical_sequence,
    )
    sequence_sha256 = hashlib.sha256(canonical_sequence.encode("ascii")).hexdigest()
    receipt = MsaSourceReceipt(
        type="precomputed-file",
        source_name=resolved.name,
        canonical_sequence_sha256=sequence_sha256,
        a3m_sha256=actual_sha256,
        a3m_size_bytes=actual_size,
        depth=actual_depth,
    )
    return ValidatedMsaArtifact(source_path=resolved, receipt=receipt)


def _verify_snapshot(snapshot: MsaInputSnapshot) -> MsaInputSnapshot:
    receipt = load_model(snapshot.receipt_path, MsaSourceReceipt)
    if receipt != snapshot.receipt:
        raise MsaArtifactError("已存在 MSA snapshot receipt 与请求不一致")
    query = _a3m_query(snapshot.a3m_path)
    if hashlib.sha256(query.encode("ascii")).hexdigest() != (
        receipt.canonical_sequence_sha256
    ):
        raise MsaArtifactError("已存在 MSA snapshot query identity 不一致")
    actual_sha256, actual_size, actual_depth = validate_a3m(
        snapshot.a3m_path,
        expected_query=query,
    )
    if (
        actual_sha256 != receipt.a3m_sha256
        or actual_size != receipt.a3m_size_bytes
        or actual_depth != receipt.depth
    ):
        raise MsaArtifactError("已存在 MSA snapshot identity 不一致")
    return snapshot


def _a3m_query(path: Path) -> str:
    parts: list[str] = []
    seen_header = False
    with path.open("r", encoding="utf-8") as handle:
        for raw in handle:
            line = raw.strip()
            if not line:
                continue
            if line.startswith(">"):
                if seen_header:
                    break
                seen_header = True
            elif seen_header:
                parts.append(line)
    return "".join(parts)


def snapshot_msa_artifact(
    *,
    context: WorkspaceContext,
    artifact: ValidatedMsaArtifact,
    destination_parent: Path,
) -> MsaInputSnapshot:
    """Create or verify an immutable project/run-local A3M input snapshot."""

    parent = context.require_write_path(
        destination_parent,
        purpose="MSA input snapshot",
    )
    identity = (
        f"{artifact.receipt.canonical_sequence_sha256[:16]}-"
        f"{artifact.receipt.a3m_sha256[:16]}"
    )
    selected = parent / identity
    a3m = selected / "target.a3m"
    receipt_path = selected / "msa-source.json"
    snapshot = MsaInputSnapshot(
        root=selected,
        a3m_path=a3m,
        receipt_path=receipt_path,
        receipt=artifact.receipt,
    )
    if selected.exists():
        return _verify_snapshot(snapshot)
    parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{identity}.creating-", dir=parent))
    try:
        staging_a3m = staging / "target.a3m"
        shutil.copyfile(artifact.source_path, staging_a3m)
        if sha256_file(staging_a3m) != artifact.receipt.a3m_sha256:
            raise MsaArtifactError("MSA source 在 snapshot 复制期间发生变化")
        dump_model(artifact.receipt, staging / "msa-source.json")
        try:
            _publish_directory_no_replace(staging, selected)
        except FileExistsError:
            shutil.rmtree(staging)
            return _verify_snapshot(snapshot)
    except Exception:
        if staging.exists():
            shutil.rmtree(staging)
        raise
    return _verify_snapshot(snapshot)


def validate_library_release(
    *,
    context: WorkspaceContext,
    release_id: str,
    verify_all_entries: bool = False,
) -> dict[str, object]:
    """Validate one registered release, optionally hashing every A3M."""

    selected_release = _require_release_id(release_id)
    release = _load_release_root(
        _library_root(context, selected_release),
        release_id=selected_release,
    )
    checked = 0
    if verify_all_entries:
        for item in release.entries:
            if not isinstance(item, MsaLibraryEntry):
                raise MsaArtifactError(
                    "全量验证只支持含 release receipt 的 MSA library 1.0"
                )
            source = _safe_library_entry(release.root, item.a3m_path)
            query = _a3m_query(source)
            actual = validate_a3m(source, expected_query=query)
            if actual != (item.a3m_sha256, item.a3m_size_bytes, item.depth):
                raise MsaArtifactError(f"MSA library entry identity 不一致: {item.a3m_path}")
            sequence_sha256 = hashlib.sha256(query.encode("ascii")).hexdigest()
            if sequence_sha256 != item.canonical_sequence_sha256:
                raise MsaArtifactError(f"MSA library query SHA-256 不一致: {item.a3m_path}")
            checked += 1
    return {
        "status": "valid",
        "release_id": release.release_id,
        "schema_version": release.schema_version,
        "entry_count": len(release.entries),
        "entries_hashed": checked,
        "library_manifest_sha256": release.manifest_sha256,
        "release_receipt_sha256": release.release_receipt_sha256,
    }


def register_library_release(
    *,
    context: WorkspaceContext,
    source: Path,
    release_id: str,
) -> Path:
    """Import a complete 1.0 release into this clone without overwriting."""

    selected_release = _require_release_id(release_id)
    source_root = source.expanduser().resolve(strict=True)
    release = _load_release_root(source_root, release_id=selected_release)
    if release.schema_version != NEW_LIBRARY_SCHEMA_VERSION:
        raise MsaArtifactError("只能注册带 release receipt 的 MSA library 1.0")
    target_parent = context.runtime_root / "databases" / "gpcr-msa"
    target = target_parent / selected_release
    if target.exists():
        raise MsaArtifactError(f"MSA library release 已存在，拒绝覆盖: {target}")
    target_parent.mkdir(parents=True, exist_ok=True)
    staging_parent = Path(
        tempfile.mkdtemp(prefix=f".{selected_release}.registering-", dir=target_parent)
    )
    staging = staging_parent / selected_release
    try:
        shutil.copytree(source_root, staging)
        copied = _load_release_root(staging, release_id=selected_release)
        for item in copied.entries:
            assert isinstance(item, MsaLibraryEntry)
            source_path = _safe_library_entry(copied.root, item.a3m_path)
            query = _a3m_query(source_path)
            actual = validate_a3m(source_path, expected_query=query)
            if actual != (item.a3m_sha256, item.a3m_size_bytes, item.depth):
                raise MsaArtifactError(f"注册复制后 entry identity 不一致: {item.a3m_path}")
            if hashlib.sha256(query.encode("ascii")).hexdigest() != (
                item.canonical_sequence_sha256
            ):
                raise MsaArtifactError(f"注册复制后 query identity 不一致: {item.a3m_path}")
        _publish_directory_no_replace(staging, target)
        staging_parent.rmdir()
    except Exception:
        if staging_parent.exists():
            shutil.rmtree(staging_parent)
        raise
    return target


__all__ = [
    "LEGACY_LIBRARY_SCHEMA_VERSION",
    "MsaArtifactError",
    "MsaInputSnapshot",
    "NEW_LIBRARY_SCHEMA_VERSION",
    "ValidatedMsaArtifact",
    "register_library_release",
    "resolve_explicit_a3m",
    "resolve_library_entry",
    "snapshot_msa_artifact",
    "validate_a3m",
    "validate_library_release",
]
