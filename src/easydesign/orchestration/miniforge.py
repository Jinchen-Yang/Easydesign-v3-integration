"""Explicit, verified installation of the workspace-local Miniforge toolchain."""

from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, ValidationError

from easydesign.core import ConfigurationError, sha256_file
from easydesign.workspace_context import WorkspaceContext

MINIFORGE_RELEASE = "26.3.2-2"
MINIFORGE_INSTALLER_NAME = f"Miniforge3-{MINIFORGE_RELEASE}-Linux-x86_64.sh"
MINIFORGE_INSTALLER_URL = (
    "https://github.com/conda-forge/miniforge/releases/download/"
    f"{MINIFORGE_RELEASE}/{MINIFORGE_INSTALLER_NAME}"
)
MINIFORGE_INSTALLER_SHA256 = (
    "42260ffe3830fb953d5eee1bbb32229ff06aa7c3833c1ed7a9a0420a95685d94"
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
    release: Literal["26.3.2-2"] = "26.3.2-2"
    installer_url: Literal[
        "https://github.com/conda-forge/miniforge/releases/download/26.3.2-2/Miniforge3-26.3.2-2-Linux-x86_64.sh"
    ] = "https://github.com/conda-forge/miniforge/releases/download/26.3.2-2/Miniforge3-26.3.2-2-Linux-x86_64.sh"
    installer_sha256: Literal[
        "42260ffe3830fb953d5eee1bbb32229ff06aa7c3833c1ed7a9a0420a95685d94"
    ] = "42260ffe3830fb953d5eee1bbb32229ff06aa7c3833c1ed7a9a0420a95685d94"
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
) -> Path:
    curl = shutil.which("curl")
    if curl is None:
        raise ConfigurationError("安装 Miniforge 需要 curl")
    staging = (
        context.runtime_root
        / "tmp"
        / f"{MINIFORGE_INSTALLER_NAME}.{uuid4().hex}.part"
    )
    context.assert_write_path(staging)
    command = [
        curl,
        "--proto",
        "=https",
        "--proto-redir",
        "=https",
        "--tlsv1.2",
        "--fail",
        "--location",
        "--show-error",
        "--retry",
        "5",
        "--retry-all-errors",
        "--output",
        str(staging),
        MINIFORGE_INSTALLER_URL,
    ]
    try:
        completed = subprocess.run(
            command,
            cwd=context.root,
            env={**os.environ, **context.child_environment()},
            check=False,
            capture_output=not show_progress,
            text=True,
        )
    except OSError as error:
        raise ConfigurationError("无法启动 curl 下载 Miniforge") from error
    if completed.returncode != 0:
        if staging.exists():
            context.quarantine(
                staging,
                operation="install-miniforge-download",
                reason=f"curl 返回 {completed.returncode}",
            )
        detail = (completed.stderr or "").strip()
        raise ConfigurationError(
            f"Miniforge 下载失败: returncode={completed.returncode}; {detail}"
        )
    actual_sha256 = sha256_file(staging)
    if actual_sha256 != MINIFORGE_INSTALLER_SHA256:
        context.quarantine(
            staging,
            operation="install-miniforge-checksum",
            reason=(
                "SHA-256 mismatch: "
                f"expected={MINIFORGE_INSTALLER_SHA256}, actual={actual_sha256}"
            ),
        )
        raise ConfigurationError("Miniforge installer SHA-256 不匹配")
    return staging


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
    installer = _download_installer(context, show_progress=show_progress)
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
        try:
            installer.unlink()
        except OSError:
            context.quarantine(
                installer,
                operation="install-miniforge-installer-cleanup",
                reason="安装成功，但已校验 installer 无法删除",
            )
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
        _quarantine_if_present(
            context,
            installer,
            operation="install-miniforge-installer",
            reason="安装或 receipt 发布未完成",
        )
        raise
