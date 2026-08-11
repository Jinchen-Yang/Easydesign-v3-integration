"""Verified, fallback-capable materialization of pinned Git source trees."""

from __future__ import annotations

import hashlib
import os
import shutil
import signal
import subprocess
import tarfile
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator

from easydesign.core import ConfigurationError, sha256_file
from easydesign.workspace_context import WorkspaceContext

from .source_policy import (
    SourceCandidate,
    SourcePolicy,
    SourceSelection,
    download_verified_file,
    load_runtime_sources,
    rank_source_candidates,
    rewritten_candidates,
)

SOURCE_RECEIPT_NAME = ".easydesign-source.json"
GIT_FETCH_TIMEOUT_SECONDS = 180


class GitArchiveLock(BaseModel):
    """Immutable archive identity plus equivalent transport candidates."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["0.1"] = "0.1"
    sha256: str
    expected_size_bytes: int = Field(gt=0)
    sources: tuple[SourceCandidate, ...] = Field(min_length=1)

    @field_validator("sha256")
    @classmethod
    def _valid_sha256(cls, value: str) -> str:
        if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
            raise ValueError("Git archive SHA-256 格式无效")
        return value


class GitSourceReceipt(BaseModel):
    """Identity and transport evidence stored beside an extracted source tree."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["0.1"] = "0.1"
    source: str
    revision: str
    content_sha256: str
    transport_source_id: str
    transport_url: str
    archive_sha256: str | None = None
    recorded_at: datetime


class GitSourceResult(BaseModel):
    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    path: Path
    revision: str
    content_sha256: str
    size_bytes: int
    source: SourceSelection


GitStatusCallback = Callable[[str], None]
GitBytesCallback = Callable[[int, int | None], None]


def directory_content_sha256(root: Path) -> str:
    """Hash source contents while excluding transport metadata."""

    digest = hashlib.sha256()
    for path in sorted(
        item
        for item in root.rglob("*")
        if item.is_file()
        and ".git" not in item.relative_to(root).parts
        and item.name != SOURCE_RECEIPT_NAME
    ):
        relative = path.relative_to(root).as_posix().encode("utf-8")
        digest.update(len(relative).to_bytes(8, "big"))
        digest.update(relative)
        digest.update(sha256_file(path).encode("ascii"))
    return digest.hexdigest()


def _directory_size(root: Path) -> int:
    return sum(path.stat().st_size for path in root.rglob("*") if path.is_file())


def _write_receipt(path: Path, receipt: GitSourceReceipt) -> None:
    with path.open("x", encoding="utf-8") as handle:
        handle.write(receipt.model_dump_json(indent=2) + "\n")


def _safe_extract_archive(archive: Path, destination: Path) -> None:
    """Extract only regular files/directories below one archive root."""

    destination.mkdir(parents=False, exist_ok=False)
    with tarfile.open(archive, mode="r:gz") as handle:
        members = handle.getmembers()
        roots: set[str] = set()
        normalized: list[tuple[tarfile.TarInfo, tuple[str, ...]]] = []
        for member in members:
            pure = PurePosixPath(member.name)
            if pure.is_absolute() or ".." in pure.parts or not pure.parts:
                raise ConfigurationError("Git archive 含不安全路径")
            roots.add(pure.parts[0])
            normalized.append((member, pure.parts))
        if len(roots) != 1:
            raise ConfigurationError("Git archive 必须只有一个顶层目录")
        for member, parts in normalized:
            relative_parts = parts[1:]
            if not relative_parts:
                if not member.isdir():
                    raise ConfigurationError("Git archive 顶层条目必须是目录")
                continue
            target = destination.joinpath(*relative_parts)
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            if not member.isfile():
                raise ConfigurationError(
                    f"Git archive 含不允许的链接或设备条目: {member.name}"
                )
            target.parent.mkdir(parents=True, exist_ok=True)
            extracted = handle.extractfile(member)
            if extracted is None:
                raise ConfigurationError(f"Git archive 文件无法读取: {member.name}")
            with extracted, target.open("xb") as output:
                shutil.copyfileobj(extracted, output)
            target.chmod(0o755 if member.mode & 0o111 else 0o644)


def _terminate_process_group(process: subprocess.Popen[bytes]) -> None:
    try:
        os.killpg(process.pid, signal.SIGTERM)
        process.wait(timeout=5)
    except (ProcessLookupError, subprocess.TimeoutExpired):
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait()


def _git_fetch(
    command: list[str],
    *,
    cwd: Path,
    environment: dict[str, str],
) -> int:
    process = subprocess.Popen(
        command,
        cwd=cwd,
        env=environment,
        start_new_session=True,
    )
    try:
        return process.wait(timeout=GIT_FETCH_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        _terminate_process_group(process)
        return 124


def _publish_archive_source(
    context: WorkspaceContext,
    *,
    asset_id: str,
    source: str,
    revision: str,
    archive_lock: GitArchiveLock,
    destination: Path,
    source_policy: SourcePolicy,
    status_callback: GitStatusCallback | None,
    progress_callback: GitBytesCallback | None,
) -> GitSourceResult:
    filename = f"{asset_id}-{revision[:12]}.tar.gz"
    archive_path = (
        context.runtime_root
        / "cache"
        / "git-archives"
        / f"{archive_lock.sha256}-{filename}"
    )

    def selected(selection: SourceSelection) -> None:
        if status_callback is not None:
            status_callback(
                f"正在获取锁定源码归档 [{selection.source_id}]: {asset_id}"
            )

    downloaded = download_verified_file(
        context,
        artifact_id=f"git-archive-{asset_id}-{revision}",
        candidates=archive_lock.sources,
        policy=source_policy,
        destination=archive_path,
        expected_sha256=archive_lock.sha256,
        expected_size_bytes=archive_lock.expected_size_bytes,
        progress_callback=progress_callback,
        source_callback=selected,
    )
    staging = context.runtime_root / "tmp" / f"source-{asset_id}-{uuid4().hex}"
    context.assert_write_path(staging)
    try:
        _safe_extract_archive(downloaded.path, staging)
        content_sha256 = directory_content_sha256(staging)
        receipt = GitSourceReceipt(
            source=source,
            revision=revision,
            content_sha256=content_sha256,
            transport_source_id=downloaded.source.source_id,
            transport_url=downloaded.source.url,
            archive_sha256=archive_lock.sha256,
            recorded_at=datetime.now(tz=UTC),
        )
        _write_receipt(staging / SOURCE_RECEIPT_NAME, receipt)
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            raise ConfigurationError(f"Git 源码目标已存在，拒绝覆盖: {destination}")
        staging.rename(destination)
    except Exception:
        if staging.exists():
            context.quarantine(
                staging,
                operation=f"source-archive-{asset_id}",
                reason="锁定源码归档提取或发布未完成",
            )
        raise
    return GitSourceResult(
        path=destination,
        revision=revision,
        content_sha256=content_sha256,
        size_bytes=_directory_size(destination),
        source=downloaded.source,
    )


def _publish_git_source(
    context: WorkspaceContext,
    *,
    asset_id: str,
    source: str,
    revision: str,
    destination: Path,
    source_policy: SourcePolicy,
    status_callback: GitStatusCallback | None,
) -> GitSourceResult:
    staging = context.runtime_root / "tmp" / f"source-{asset_id}-{uuid4().hex}"
    context.assert_write_path(staging)
    environment = {
        **context.subprocess_environment(),
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_HTTP_LOW_SPEED_LIMIT": "1024",
        "GIT_HTTP_LOW_SPEED_TIME": "30",
    }
    errors: list[str] = []
    try:
        initialize = subprocess.run(
            ["git", "init", "--quiet", str(staging)],
            cwd=context.root,
            env=environment,
            check=False,
        )
        if initialize.returncode != 0:
            raise ConfigurationError(f"Git 源码 init 失败: {asset_id}")
        catalog = load_runtime_sources(context)
        candidates = rank_source_candidates(
            rewritten_candidates(
                source,
                source_id="official-git",
                rewrites=catalog.asset_rewrites,
            ),
            source_policy,
        )
        selected: SourceSelection | None = None
        for candidate in candidates:
            for mode_id, http_version in (
                ("http1", "HTTP/1.1"),
                ("default-http", None),
            ):
                if status_callback is not None:
                    status_callback(
                        f"正在获取锁定 Git commit [{candidate.source_id}-{mode_id}]: "
                        f"{asset_id}"
                    )
                command = ["git"]
                if http_version is not None:
                    command.extend(["-c", f"http.version={http_version}"])
                command.extend(
                    [
                        "-C",
                        str(staging),
                        "fetch",
                        "--depth",
                        "1",
                        "--no-tags",
                        candidate.url,
                        revision,
                    ]
                )
                returncode = _git_fetch(
                    command,
                    cwd=context.root,
                    environment=environment,
                )
                if returncode == 0:
                    selected = SourceSelection(
                        source_id=f"{candidate.source_id}-{mode_id}",
                        url=candidate.url,
                    )
                    break
                errors.append(f"{candidate.source_id}-{mode_id}: returncode={returncode}")
            if selected is not None:
                break
        if selected is None:
            raise ConfigurationError(
                f"Git 源码所有候选方式均失败: {asset_id}; {'; '.join(errors[-6:])}"
            )
        checkout = subprocess.run(
            ["git", "-C", str(staging), "checkout", "--detach", "FETCH_HEAD"],
            cwd=context.root,
            env=environment,
            check=False,
        )
        if checkout.returncode != 0:
            raise ConfigurationError(f"Git 源码 revision 不可用: {asset_id}")
        actual_revision = subprocess.run(
            ["git", "-C", str(staging), "rev-parse", "HEAD"],
            cwd=context.root,
            env=environment,
            capture_output=True,
            text=True,
            check=True,
            timeout=30,
        ).stdout.strip()
        if actual_revision != revision:
            raise ConfigurationError(f"Git 源码 commit 不一致: {asset_id}")
        content_sha256 = directory_content_sha256(staging)
        _write_receipt(
            staging / SOURCE_RECEIPT_NAME,
            GitSourceReceipt(
                source=source,
                revision=revision,
                content_sha256=content_sha256,
                transport_source_id=selected.source_id,
                transport_url=selected.url,
                recorded_at=datetime.now(tz=UTC),
            ),
        )
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            raise ConfigurationError(f"Git 源码目标已存在，拒绝覆盖: {destination}")
        staging.rename(destination)
    except Exception:
        if staging.exists():
            context.quarantine(
                staging,
                operation=f"source-git-{asset_id}",
                reason="Git checkout 或发布未完成",
            )
        raise
    return GitSourceResult(
        path=destination,
        revision=revision,
        content_sha256=content_sha256,
        size_bytes=_directory_size(destination),
        source=selected,
    )


def verify_git_source_identity(
    destination: Path,
    *,
    revision: str,
    source: str | None = None,
    environment: dict[str, str] | None = None,
) -> GitSourceResult:
    """Verify a generic source receipt or an explicit, self-contained checkout."""

    if not destination.is_dir():
        raise ConfigurationError(f"Git 源码目录不存在: {destination}")
    content_sha256 = directory_content_sha256(destination)
    receipt_path = destination / SOURCE_RECEIPT_NAME
    if receipt_path.is_file():
        try:
            receipt = GitSourceReceipt.model_validate_json(
                receipt_path.read_text(encoding="utf-8")
            )
        except (OSError, ValueError) as error:
            raise ConfigurationError("Git 源码 receipt 损坏") from error
        if (
            (source is not None and receipt.source != source)
            or receipt.revision != revision
            or receipt.content_sha256 != content_sha256
        ):
            raise ConfigurationError("Git 源码 receipt 与现有内容不一致")
        return GitSourceResult(
            path=destination,
            revision=revision,
            content_sha256=content_sha256,
            size_bytes=_directory_size(destination),
            source=SourceSelection(
                source_id="workspace-existing",
                url="workspace-cache://verified-git-source",
            ),
        )
    # Never allow ``git -C`` to discover the EasyDesign repository (or any
    # other parent checkout) when an extracted source snapshot lacks a receipt.
    if not (destination / ".git").is_dir():
        raise ConfigurationError("Git 源码缺少统一 receipt 或自身 .git 目录")
    git_environment = dict(os.environ if environment is None else environment)
    git_environment["GIT_CEILING_DIRECTORIES"] = str(destination.parent.resolve())
    revision_check = subprocess.run(
        ["git", "-C", str(destination), "rev-parse", "HEAD"],
        env=git_environment,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    clean_check = subprocess.run(
        [
            "git",
            "-C",
            str(destination),
            "status",
            "--porcelain",
            "--untracked-files=all",
        ],
        env=git_environment,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    if (
        revision_check.returncode != 0
        or revision_check.stdout.strip() != revision
        or clean_check.returncode != 0
        or clean_check.stdout.strip()
    ):
        raise ConfigurationError("现有 Git 源码 revision 不一致或工作树不干净")
    return GitSourceResult(
        path=destination,
        revision=revision,
        content_sha256=content_sha256,
        size_bytes=_directory_size(destination),
        source=SourceSelection(
            source_id="workspace-existing",
            url="workspace-cache://verified-git-source",
        ),
    )


def verify_existing_git_source(
    context: WorkspaceContext,
    *,
    source: str,
    revision: str,
    destination: Path,
) -> GitSourceResult:
    """Verify either an archived source receipt or a clean Git checkout."""

    return verify_git_source_identity(
        destination,
        source=source,
        revision=revision,
        environment=context.subprocess_environment(),
    )


def materialize_git_source(
    context: WorkspaceContext,
    *,
    asset_id: str,
    source: str,
    revision: str,
    archive_lock: GitArchiveLock | None,
    destination: Path,
    source_policy: SourcePolicy,
    status_callback: GitStatusCallback | None = None,
    progress_callback: GitBytesCallback | None = None,
) -> GitSourceResult:
    """Materialize once, preferring a resumable archive before Git smart HTTP."""

    context.ensure_layout()
    context.assert_write_path(destination)
    if destination.exists():
        return verify_existing_git_source(
            context,
            source=source,
            revision=revision,
            destination=destination,
        )
    archive_error: Exception | None = None
    if archive_lock is not None:
        try:
            return _publish_archive_source(
                context,
                asset_id=asset_id,
                source=source,
                revision=revision,
                archive_lock=archive_lock,
                destination=destination,
                source_policy=source_policy,
                status_callback=status_callback,
                progress_callback=progress_callback,
            )
        except Exception as error:
            archive_error = error
            if status_callback is not None:
                status_callback(
                    f"锁定源码归档不可用，自动切换 Git transport: {asset_id}"
                )
    try:
        return _publish_git_source(
            context,
            asset_id=asset_id,
            source=source,
            revision=revision,
            destination=destination,
            source_policy=source_policy,
            status_callback=status_callback,
        )
    except Exception as git_error:
        archive_detail = "未配置归档" if archive_error is None else str(archive_error)
        raise ConfigurationError(
            f"锁定源码所有安全获取方式均失败: {asset_id}; "
            f"archive={archive_detail}; git={git_error}"
        ) from git_error
