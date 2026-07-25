"""跨平台、显式且不进入 run artifact 的本机 runtime profile。"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import yaml  # type: ignore[import-untyped]
from platformdirs import user_config_path
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from easydesign.core import ConfigurationError, RuntimeProfileRef, sha256_file
from easydesign.core.artifacts import ID_PATTERN

PROFILE_ENVIRONMENT_VARIABLE = "EASYDESIGN_PROFILE"
DEFAULT_PROFILE_NAME = "profile.yaml"


class ProtenixV2Runtime(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    executable: Path
    model_root: Path
    model_checkpoint: Path
    cuda_visible_devices: str | None = None

    @field_validator("executable", "model_root", "model_checkpoint")
    @classmethod
    def require_absolute_path(cls, value: Path) -> Path:
        if not value.is_absolute():
            raise ValueError("Protenix runtime 路径必须是绝对路径")
        return value


class PyMOLPseRuntime(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    python: Path
    timeout_seconds: float = Field(default=120.0, gt=0)

    @field_validator("python")
    @classmethod
    def require_absolute_path(cls, value: Path) -> Path:
        if not value.is_absolute():
            raise ValueError("PyMOL Python 必须是绝对路径")
        return value


class ScanNetEpitopeRuntime(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    python: Path
    repository_root: Path
    execution_device: Literal["cpu", "gpu"] = "cpu"
    gpu_device: int = Field(default=0, ge=0)
    timeout_seconds: float = Field(default=1800.0, gt=0)

    @field_validator("python", "repository_root")
    @classmethod
    def require_absolute_path(cls, value: Path) -> Path:
        if not value.is_absolute():
            raise ValueError("ScanNet runtime 路径必须是绝对路径")
        return value


class BoltzGenRuntime(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    executable: Path
    repository_root: Path
    cache_root: Path
    timeout_seconds: float = Field(default=300.0, gt=0)
    generation_timeout_seconds: float = Field(default=172_800.0, gt=0)
    data_loader_workers: int = Field(default=4, ge=0, le=64)
    validation_workers: int = Field(default=4, ge=1, le=8)
    offline_mode: bool = True

    @field_validator("executable", "repository_root", "cache_root")
    @classmethod
    def require_absolute_path(cls, value: Path) -> Path:
        if not value.is_absolute():
            raise ValueError("BoltzGen runtime 路径必须是绝对路径")
        return value


class RuntimeBackends(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    protenix_v2: ProtenixV2Runtime | None = None
    pymol_pse: PyMOLPseRuntime | None = None
    scannet_epitope: ScanNetEpitopeRuntime | None = None
    boltzgen: BoltzGenRuntime | None = None


class RuntimeProfile(BaseModel):
    """只保存机器部署信息；科学参数仍属于 easydesign.yaml。"""

    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    schema_version: str = Field(default="0.1", pattern=r"^0\.1$")
    profile_id: str = Field(default="local", pattern=ID_PATTERN)
    runs_root: Path | None = None
    backends: RuntimeBackends = RuntimeBackends()

    @field_validator("runs_root")
    @classmethod
    def require_absolute_runs_root(cls, value: Path | None) -> Path | None:
        if value is not None and not value.is_absolute():
            raise ValueError("runs_root 必须是绝对路径")
        return value


@dataclass(frozen=True, slots=True)
class LoadedRuntimeProfile:
    path: Path
    profile: RuntimeProfile
    identity: RuntimeProfileRef


def default_runtime_profile_path() -> Path:
    """返回当前操作系统的用户级默认 profile，不创建目录。"""

    return user_config_path("easydesign", appauthor=False) / DEFAULT_PROFILE_NAME


def resolve_runtime_profile_path(explicit_path: Path | None = None) -> Path:
    """只解析显式路径、单个环境变量或默认位置；不扫描环境。"""

    if explicit_path is not None:
        return explicit_path.expanduser()
    environment_path = os.environ.get(PROFILE_ENVIRONMENT_VARIABLE)
    if environment_path:
        return Path(environment_path).expanduser()
    return default_runtime_profile_path()


def _profile_payload(profile: RuntimeProfile) -> dict[str, object]:
    return profile.model_dump(mode="json", exclude_none=True)


def initialize_runtime_profile(
    path: Path | None = None,
    *,
    profile_id: str = "local",
    runs_root: Path | None = None,
) -> Path:
    """排他创建一个空 backend profile 模板；不会探测本机工具。"""

    destination = resolve_runtime_profile_path(path).resolve()
    profile = RuntimeProfile(profile_id=profile_id, runs_root=runs_root)
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        with destination.open("x", encoding="utf-8", newline="\n") as handle:
            yaml.safe_dump(
                _profile_payload(profile),
                handle,
                allow_unicode=True,
                sort_keys=False,
            )
    except FileExistsError as error:
        raise ConfigurationError(f"Runtime profile 已存在，禁止覆盖: {destination}") from error
    return destination


def load_runtime_profile(path: Path | None = None) -> LoadedRuntimeProfile:
    selected = resolve_runtime_profile_path(path)
    try:
        resolved = selected.resolve(strict=True)
        raw = yaml.safe_load(resolved.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, yaml.YAMLError) as error:
        raise ConfigurationError(
            f"Runtime profile 无法读取: path={selected}, error={error}"
        ) from error
    if not isinstance(raw, dict):
        raise ConfigurationError("Runtime profile 顶层必须是 mapping")
    try:
        profile = RuntimeProfile.model_validate(raw)
    except ValidationError as error:
        raise ConfigurationError(f"Runtime profile 校验失败: {error}") from error
    return LoadedRuntimeProfile(
        path=resolved,
        profile=profile,
        identity=RuntimeProfileRef(
            profile_id=profile.profile_id,
            sha256=sha256_file(resolved),
        ),
    )
