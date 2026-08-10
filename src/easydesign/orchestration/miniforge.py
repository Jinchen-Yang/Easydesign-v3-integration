"""Explicit, verified installation of the workspace-local Miniforge toolchain."""

from __future__ import annotations

import json
import os
import platform
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, ValidationError

from easydesign.core import ConfigurationError
from easydesign.workspace_context import WorkspaceContext

from .source_policy import (
    SourcePolicy,
    SourceSelection,
    download_verified_file,
    load_runtime_sources,
)

MINIFORGE_RELEASE = "26.3.2-3"
MINIFORGE_INSTALLER_NAME = f"Miniforge3-{MINIFORGE_RELEASE}-Linux-x86_64.sh"
MINIFORGE_INSTALLER_URL = (
    "https://github.com/conda-forge/miniforge/releases/download/"
    f"{MINIFORGE_RELEASE}/{MINIFORGE_INSTALLER_NAME}"
)
MINIFORGE_INSTALLER_SHA256 = (
    "848194851a98903134187fbb4ab50efe87b003e0c0f808f97644b7524a62bf2c"
)
MINIFORGE_PREFIX = Path("runtime/tools/miniforge3")
MINIFORGE_RELEASE_PREFIX = Path(
    f"runtime/tools/miniforge3-{MINIFORGE_RELEASE}-{MINIFORGE_INSTALLER_SHA256[:12]}"
)
MINIFORGE_RECEIPT = (
    Path("runtime/state/tools/miniforge")
    / f"{MINIFORGE_RELEASE}-{MINIFORGE_INSTALLER_SHA256[:12]}.json"
)


class MiniforgeReceipt(BaseModel):
    """Immutable identity and probe evidence for the local toolchain."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["0.1"] = "0.1"
    tool_id: Literal["miniforge"] = "miniforge"
    release: Literal["26.3.2-3"] = "26.3.2-3"
    installer_url: Literal[
        "https://github.com/conda-forge/miniforge/releases/download/26.3.2-3/Miniforge3-26.3.2-3-Linux-x86_64.sh"
    ] = "https://github.com/conda-forge/miniforge/releases/download/26.3.2-3/Miniforge3-26.3.2-3-Linux-x86_64.sh"
    installer_sha256: Literal[
        "848194851a98903134187fbb4ab50efe87b003e0c0f808f97644b7524a62bf2c"
    ] = "848194851a98903134187fbb4ab50efe87b003e0c0f808f97644b7524a62bf2c"
    source_policy: SourcePolicy = "official"
    transport_source_id: str = "official-github"
    transport_url: str = MINIFORGE_INSTALLER_URL
    prefix: Path = MINIFORGE_PREFIX
    release_prefix: Path = MINIFORGE_RELEASE_PREFIX
    conda_executable: Path = MINIFORGE_PREFIX / "bin/conda"
    conda_version: str
    installed_at: datetime


class MiniforgeInstallResult(BaseModel):
    """User-facing result for an explicit Miniforge installation request."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    status: Literal["installed", "already-installed"]
    receipt: MiniforgeReceipt
    receipt_path: Path


def local_miniforge_conda(context: WorkspaceContext) -> Path:
    """Return the expected repository-local Conda executable path."""

    return context.root / MINIFORGE_PREFIX / "bin/conda"


def _receipt_path(context: WorkspaceContext) -> Path:
    return context.root / MINIFORGE_RECEIPT


def _probe_conda(context: WorkspaceContext, conda: Path) -> str:
    try:
        completed = subprocess.run(
            [str(conda), "--version"],
            cwd=context.root,
            env={**os.environ, **context.child_environment()},
            check=False,
            capture_output=True,
            text=True,
            timeout=60,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise ConfigurationError(f"Miniforge Conda 探针失败: {conda}") from error
    version = (completed.stdout or completed.stderr).strip()
    if completed.returncode != 0 or not version.startswith("conda "):
        raise ConfigurationError(
            f"Miniforge Conda 探针失败: returncode={completed.returncode}, output={version}"
        )
    return version


def verify_miniforge(context: WorkspaceContext) -> MiniforgeReceipt:
    """Verify the receipt, fixed paths, and live Conda probe without mutation."""

    path = _receipt_path(context)
    try:
        receipt = MiniforgeReceipt.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValidationError) as error:
        raise ConfigurationError(f"Miniforge receipt 无法校验: {path}") from error
    expected_prefix = context.root / MINIFORGE_PREFIX
    expected_release_prefix = context.root / MINIFORGE_RELEASE_PREFIX
    expected_conda = local_miniforge_conda(context)
    if context.root / receipt.prefix != expected_prefix:
        raise ConfigurationError("Miniforge receipt prefix 与当前工作区不一致")
    if context.root / receipt.conda_executable != expected_conda:
        raise ConfigurationError("Miniforge receipt Conda 路径与当前工作区不一致")
    if context.root / receipt.release_prefix != expected_release_prefix:
        raise ConfigurationError("Miniforge receipt release prefix 与当前工作区不一致")
    if (
        not expected_prefix.is_symlink()
        or expected_prefix.resolve(strict=False) != expected_release_prefix
        or not expected_release_prefix.is_dir()
        or expected_release_prefix.is_symlink()
        or not expected_conda.is_file()
    ):
        raise ConfigurationError("Miniforge receipt 存在，但本地工具目录不完整")
    version = _probe_conda(context, expected_conda)
    if version != receipt.conda_version:
        raise ConfigurationError(
            "Miniforge Conda 版本与安装 receipt 不一致；拒绝静默接受环境漂移"
        )
    return receipt


def miniforge_status(context: WorkspaceContext) -> MiniforgeReceipt | None:
    """Return a verified receipt, or None only when nothing has been installed."""

    receipt_exists = _receipt_path(context).is_file()
    prefix_path = context.root / MINIFORGE_PREFIX
    release_prefix_path = context.root / MINIFORGE_RELEASE_PREFIX
    prefix_exists = prefix_path.exists() or prefix_path.is_symlink()
    release_prefix_exists = (
        release_prefix_path.exists() or release_prefix_path.is_symlink()
    )
    if not receipt_exists and not prefix_exists and not release_prefix_exists:
        return None
    if receipt_exists and prefix_exists and release_prefix_exists:
        return verify_miniforge(context)
    raise ConfigurationError(
        "Miniforge 目录与 receipt 不完整；拒绝覆盖，请检查 runtime/tools 和 runtime/state"
    )


def _download_installer(
    context: WorkspaceContext,
    *,
    show_progress: bool,
    source_policy: SourcePolicy,
) -> tuple[Path, SourceSelection]:
    catalog = load_runtime_sources(context)
    destination = (
        context.runtime_root
        / "cache"
        / "downloads"
        / "miniforge"
        / MINIFORGE_INSTALLER_NAME
    )

    def progress(completed: int, total: int | None) -> None:
        if not show_progress:
            return
        total_text = "?" if total is None else str(total)
        print(f"\rMiniforge 下载: {completed}/{total_text} bytes", end="", flush=True)

    result = download_verified_file(
        context,
        artifact_id=f"miniforge-{MINIFORGE_RELEASE}-linux-x86_64",
        candidates=catalog.miniforge,
        policy=source_policy,
        destination=destination,
        expected_sha256=MINIFORGE_INSTALLER_SHA256,
        expected_size_bytes=105_172_629,
        progress_callback=progress if show_progress else None,
    )
    if show_progress:
        print()
    return result.path, result.source


def _quarantine_if_present(
    context: WorkspaceContext,
    path: Path,
    *,
    operation: str,
    reason: str,
) -> None:
    if path.exists():
        context.quarantine(path, operation=operation, reason=reason)


def install_miniforge(
    context: WorkspaceContext,
    *,
    show_progress: bool = True,
    source_policy: SourcePolicy = "auto",
) -> MiniforgeInstallResult:
    """Install the pinned Miniforge only after an explicit CLI request."""

    if platform.system() != "Linux" or platform.machine().lower() not in {
        "x86_64",
        "amd64",
    }:
        raise ConfigurationError("当前 Miniforge 锁只支持 Linux x86-64")
    context.ensure_layout()
    prefix = context.root / MINIFORGE_PREFIX
    release_prefix = context.root / MINIFORGE_RELEASE_PREFIX
    receipt_path = _receipt_path(context)
    context.assert_write_path(prefix)
    context.assert_write_path(release_prefix)
    context.assert_write_path(receipt_path)
    existing = miniforge_status(context)
    if existing is not None:
        return MiniforgeInstallResult(
            status="already-installed",
            receipt=existing,
            receipt_path=receipt_path.relative_to(context.root),
        )

    release_prefix.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    installer, selected_source = _download_installer(
        context,
        show_progress=show_progress,
        source_policy=source_policy,
    )
    alias_published = False
    try:
        completed = subprocess.run(
            ["/bin/bash", str(installer), "-b", "-p", str(release_prefix)],
            cwd=context.root,
            env={**os.environ, **context.child_environment()},
            check=False,
            capture_output=not show_progress,
            text=True,
        )
        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout or "").strip()
            raise ConfigurationError(
                f"Miniforge installer 返回 {completed.returncode}; {detail}"
            )
        conda = release_prefix / "bin/conda"
        version = _probe_conda(context, conda)
        receipt = MiniforgeReceipt(
            source_policy=source_policy,
            transport_source_id=selected_source.source_id,
            transport_url=selected_source.url,
            conda_version=version,
            installed_at=datetime.now(tz=UTC),
        )
        if prefix.exists() or prefix.is_symlink():
            raise ConfigurationError("Miniforge 发布入口已存在，拒绝覆盖")
        prefix.symlink_to(MINIFORGE_RELEASE_PREFIX.name, target_is_directory=True)
        alias_published = True
        alias_version = _probe_conda(context, local_miniforge_conda(context))
        if alias_version != version:
            raise ConfigurationError("Miniforge 原子发布后的 Conda 探针不一致")
        with receipt_path.open("x", encoding="utf-8") as handle:
            handle.write(
                json.dumps(receipt.model_dump(mode="json"), ensure_ascii=False, indent=2)
                + "\n"
            )
            handle.flush()
            os.fsync(handle.fileno())
        return MiniforgeInstallResult(
            status="installed",
            receipt=receipt,
            receipt_path=receipt_path.relative_to(context.root),
        )
    except Exception:
        if alias_published and prefix.is_symlink():
            prefix.unlink()
        _quarantine_if_present(
            context,
            receipt_path,
            operation="install-miniforge-receipt",
            reason="receipt 发布未完成",
        )
        _quarantine_if_present(
            context,
            release_prefix,
            operation="install-miniforge-prefix",
            reason="安装或 Conda 探针未完成",
        )
        raise
