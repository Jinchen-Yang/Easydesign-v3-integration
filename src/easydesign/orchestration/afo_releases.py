"""Immutable AFO release catalog and verified bundle materialization."""

from __future__ import annotations

import shutil
import subprocess
import tarfile
import tempfile
from pathlib import Path, PurePosixPath
from typing import Literal, Self

import yaml  # type: ignore[import-untyped]
from pydantic import BaseModel, ConfigDict, Field, model_validator

from easydesign.core import ConfigurationError
from easydesign.core.artifacts import SHA256_PATTERN
from easydesign.workspace_context import WorkspaceContext

from .runtime_components import (
    OpenFold3InstallResult,
    install_openfold3_component,
    load_openfold3_bundle,
)
from .source_policy import SourceCandidate, SourcePolicy, download_verified_file


class AfoBundleArtifact(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    sha256: str = Field(pattern=SHA256_PATTERN)
    size_bytes: int = Field(gt=0)
    sources: tuple[SourceCandidate, ...] = Field(min_length=1)
    archive_format: Literal["tar.zst"] = "tar.zst"


class AfoReleaseEntry(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    release_id: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    channel: Literal["candidate", "stable"]
    backend_version: str = Field(
        pattern=r"^[0-9]+\.[0-9]+\.[0-9]+(?:[-+][0-9A-Za-z.-]+)?$"
    )
    runner_commit: str = Field(pattern=r"^[0-9a-f]{40}$")
    wheel_sha256: str = Field(pattern=SHA256_PATTERN)
    raw_checkpoint_sha256: str = Field(pattern=SHA256_PATTERN)
    bundle: AfoBundleArtifact | None = None
    validation_report_sha256: str | None = Field(default=None, pattern=SHA256_PATTERN)
    approval_receipt_sha256: str | None = Field(default=None, pattern=SHA256_PATTERN)

    @model_validator(mode="after")
    def stable_is_approved_and_installable(self) -> Self:
        if self.channel == "stable" and (
            self.bundle is None
            or self.validation_report_sha256 is None
            or self.approval_receipt_sha256 is None
        ):
            raise ValueError("AFO stable release 必须可安装且绑定验证报告与批准 receipt")
        return self


class AfoReleaseCatalog(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["0.1"] = "0.1"
    releases: tuple[AfoReleaseEntry, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_releases(self) -> Self:
        release_ids = [item.release_id for item in self.releases]
        if len(release_ids) != len(set(release_ids)):
            raise ValueError("AFO release_id 不能重复")
        stable = [item for item in self.releases if item.channel == "stable"]
        if len(stable) > 1:
            raise ValueError("AFO catalog 同时只能声明一个 stable release")
        return self

    def resolve(
        self,
        *,
        release_id: str | None = None,
        channel: Literal["candidate", "stable"] = "stable",
    ) -> AfoReleaseEntry:
        selected = (
            [item for item in self.releases if item.release_id == release_id]
            if release_id is not None
            else [item for item in self.releases if item.channel == channel]
        )
        if len(selected) != 1:
            identity = release_id if release_id is not None else channel
            raise ConfigurationError(f"AFO catalog 无唯一可用 release: {identity}")
        return selected[0]


def load_afo_release_catalog(
    context: WorkspaceContext | None = None,
) -> AfoReleaseCatalog:
    selected = WorkspaceContext.discover() if context is None else context
    path = selected.root / "config/afo-releases.yaml"
    try:
        return AfoReleaseCatalog.model_validate(
            yaml.safe_load(path.read_text(encoding="utf-8"))
        )
    except (OSError, UnicodeDecodeError, ValueError, yaml.YAMLError) as error:
        raise ConfigurationError(f"AFO release catalog 无法校验: {path}") from error


def _safe_extract_tar(archive: Path, destination: Path) -> Path:
    destination.mkdir(parents=False, exist_ok=False)
    with tarfile.open(archive, mode="r:") as handle:
        for member in handle.getmembers():
            pure = PurePosixPath(member.name)
            if pure.is_absolute() or ".." in pure.parts or not pure.parts:
                raise ConfigurationError("AFO bundle archive 含不安全路径")
            target = destination.joinpath(*pure.parts)
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            if not member.isfile():
                raise ConfigurationError(
                    f"AFO bundle archive 含链接或设备条目: {member.name}"
                )
            target.parent.mkdir(parents=True, exist_ok=True)
            extracted = handle.extractfile(member)
            if extracted is None:
                raise ConfigurationError(f"AFO bundle archive 无法读取: {member.name}")
            with extracted, target.open("xb") as output:
                shutil.copyfileobj(extracted, output)
            target.chmod(0o755 if member.mode & 0o111 else 0o644)
    return destination


def materialize_afo_bundle(
    release: AfoReleaseEntry,
    *,
    source_policy: SourcePolicy = "auto",
    context: WorkspaceContext | None = None,
) -> Path:
    selected = WorkspaceContext.discover() if context is None else context
    if release.bundle is None:
        raise ConfigurationError(
            f"AFO release 尚未发布预转换 bundle: {release.release_id}"
        )
    destination = (
        selected.runtime_root
        / "imports/afo"
        / release.release_id
        / release.bundle.sha256
    )
    if destination.is_dir():
        load_openfold3_bundle(destination)
        return destination
    archive = destination.with_suffix(".tar.zst")
    download_verified_file(
        selected,
        artifact_id=f"afo-bundle-{release.release_id}",
        candidates=release.bundle.sources,
        policy=source_policy,
        destination=archive,
        expected_sha256=release.bundle.sha256,
        expected_size_bytes=release.bundle.size_bytes,
    )
    zstd = shutil.which("zstd")
    if zstd is None:
        raise ConfigurationError("安装 AFO catalog bundle 需要 zstd executable")
    staging = Path(
        tempfile.mkdtemp(prefix="afo-bundle-", dir=selected.runtime_root / "tmp")
    )
    tar_path = staging / "bundle.tar"
    extracted = staging / "bundle"
    try:
        with tar_path.open("xb") as output:
            completed = subprocess.run(
                [zstd, "--decompress", "--stdout", str(archive)],
                check=False,
                stdout=output,
                stderr=subprocess.PIPE,
            )
        if completed.returncode != 0:
            raise ConfigurationError(
                "AFO bundle 解压失败: "
                + completed.stderr.decode("utf-8", errors="replace")
            )
        _safe_extract_tar(tar_path, extracted)
        manifest = load_openfold3_bundle(extracted)[1]
        if (
            manifest.release_id != release.release_id
            or manifest.backend_version != release.backend_version
            or manifest.runner_commit != release.runner_commit
            or manifest.wheel_sha256 != release.wheel_sha256
            or manifest.raw_checkpoint_sha256 != release.raw_checkpoint_sha256
        ):
            raise ConfigurationError("AFO catalog 与下载 bundle identity 不一致")
        destination.parent.mkdir(parents=True, exist_ok=True)
        extracted.rename(destination)
        tar_path.unlink()
        staging.rmdir()
        return destination
    except Exception as error:
        if staging.exists():
            selected.quarantine(
                staging,
                operation="afo-bundle-materialization",
                reason=str(error),
            )
        raise


def install_stable_afo_if_available(
    *,
    source_policy: SourcePolicy = "auto",
    context: WorkspaceContext | None = None,
) -> OpenFold3InstallResult | None:
    """Install and activate the single stable AFO release, if one is published."""

    selected = WorkspaceContext.discover() if context is None else context
    catalog = load_afo_release_catalog(selected)
    stable = tuple(item for item in catalog.releases if item.channel == "stable")
    if not stable:
        return None
    bundle = materialize_afo_bundle(
        stable[0],
        source_policy=source_policy,
        context=selected,
    )
    return install_openfold3_component(bundle, activate=True, context=selected)


__all__ = [
    "AfoReleaseCatalog",
    "AfoReleaseEntry",
    "load_afo_release_catalog",
    "materialize_afo_bundle",
    "install_stable_afo_if_available",
]
