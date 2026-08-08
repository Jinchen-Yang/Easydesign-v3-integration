"""Explicit local-only runtime profile.

The VS Code product never installs scientific environments and never resolves
remote executors. runtime link writes absolute, read-only backend paths after
verifying the source runtime registries.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal

import yaml  # type: ignore[import-untyped]
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from easydesign.core import ConfigurationError, RuntimeProfileRef, sha256_file
from easydesign.workspace_context import WorkspaceContext

PROFILE_ENVIRONMENT_VARIABLE = "EASYDESIGN_PROFILE"
DEFAULT_PROFILE_NAME = "profile.yaml"


class ProtenixV2Runtime(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    executable: Path
    model_root: Path
    model_checkpoint: Path
    cuda_visible_devices: str | None = None
    extra_environment: tuple[tuple[str, str], ...] = ()

    @field_validator("executable", "model_root", "model_checkpoint")
    @classmethod
    def require_absolute_path(cls, value: Path) -> Path:
        if not value.is_absolute():
            raise ValueError("Protenix runtime 路径必须是绝对路径")
        return value

    @field_validator("extra_environment")
    @classmethod
    def validate_extra_environment(
        cls, value: tuple[tuple[str, str], ...]
    ) -> tuple[tuple[str, str], ...]:
        keys = [key for key, _ in value]
        if len(keys) != len(set(keys)) or any(
            not key or not item for key, item in value
        ):
            raise ValueError("Protenix extra_environment 必须使用唯一且非空的键值")
        return value


class OpenFold3Af3JaxRuntime(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    python: Path
    runner: Path
    model_root: Path
    converted_weight: Path
    cache_root: Path
    raw_checkpoint_sha256: str
    converted_weight_sha256: str
    wheel_sha256: str
    runner_commit: str
    environment_lock_sha256: str
    cuda_visible_devices: str | None = None
    msa_server_url: str = "https://api.colabfold.com"
    msa_timeout_seconds: int = Field(default=3600, ge=1)
    prediction_timeout_seconds: int = Field(default=14_400, ge=1)
    extra_environment: tuple[tuple[str, str], ...] = ()

    @field_validator("python", "runner", "model_root", "converted_weight", "cache_root")
    @classmethod
    def require_absolute_path(cls, value: Path) -> Path:
        if not value.is_absolute():
            raise ValueError("OpenFold3 runtime 路径必须是绝对路径")
        return value

    @field_validator(
        "raw_checkpoint_sha256",
        "converted_weight_sha256",
        "wheel_sha256",
        "environment_lock_sha256",
    )
    @classmethod
    def require_sha256(cls, value: str) -> str:
        if len(value) != 64 or any(
            character not in "0123456789abcdef" for character in value
        ):
            raise ValueError("OpenFold3 identity 必须是小写 SHA-256")
        return value

    @field_validator("extra_environment")
    @classmethod
    def validate_extra_environment(
        cls, value: tuple[tuple[str, str], ...]
    ) -> tuple[tuple[str, str], ...]:
        keys = [key for key, _ in value]
        if len(keys) != len(set(keys)) or any(
            not key or not item for key, item in value
        ):
            raise ValueError("OpenFold3 extra_environment 必须使用唯一且非空的键值")
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


class TnpRuntime(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    python: Path
    executable: Path
    repository_root: Path
    timeout_seconds: float = Field(default=86_400.0, gt=0)
    ncores: int = Field(default=4, ge=1)

    @field_validator("python", "executable", "repository_root")
    @classmethod
    def require_absolute_path(cls, value: Path) -> Path:
        if not value.is_absolute():
            raise ValueError("TNP runtime 路径必须是绝对路径")
        return value


class RuntimeBackends(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    protenix_v2: ProtenixV2Runtime | None = None
    openfold3_af3_jax: OpenFold3Af3JaxRuntime | None = None
    pymol_pse: PyMOLPseRuntime | None = None
    scannet_epitope: ScanNetEpitopeRuntime | None = None
    boltzgen_validation: BoltzGenRuntime | None = None
    boltzgen: BoltzGenRuntime | None = None
    tnp: TnpRuntime | None = None


class RuntimeProfile(BaseModel):
    """Machine-local backend paths; never part of scientific configuration."""

    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    schema_version: Literal["0.1", "0.2"] = "0.2"
    profile_id: str = Field(default="local-linked", pattern=r"^[a-z0-9][a-z0-9._-]*$")
    runs_root: Path
    runtime_link_source: Path | None = None
    runtime_linked_at: datetime | None = None
    backends: RuntimeBackends = RuntimeBackends()

    @field_validator("runs_root")
    @classmethod
    def require_absolute_runs_root(cls, value: Path) -> Path:
        if not value.is_absolute():
            raise ValueError("runs_root 必须是绝对路径")
        return value

    @field_validator("runtime_link_source")
    @classmethod
    def require_absolute_link_source(cls, value: Path | None) -> Path | None:
        if value is not None and not value.is_absolute():
            raise ValueError("runtime_link_source 必须是绝对路径")
        return value


@dataclass(frozen=True, slots=True)
class LoadedRuntimeProfile:
    path: Path
    profile: RuntimeProfile
    identity: RuntimeProfileRef


def default_runtime_profile_path() -> Path:
    return WorkspaceContext.discover().profile_path


def resolve_runtime_profile_path(explicit_path: Path | None = None) -> Path:
    return (
        explicit_path.expanduser()
        if explicit_path is not None
        else default_runtime_profile_path()
    )


def _latest_profile_path(path: Path) -> Path:
    revisions = sorted(path.with_name(f"{path.name}.revisions").glob("revision-*.yaml"))
    return revisions[-1] if revisions else path


def initialize_runtime_profile(
    path: Path | None = None,
    *,
    profile_id: str = "local-test",
    runs_root: Path | None = None,
) -> Path:
    """Create an empty local profile for tests; real users run runtime link."""

    destination = resolve_runtime_profile_path(path).resolve()
    context = WorkspaceContext.discover(destination.parent)
    selected_runs = context.runs_root if runs_root is None else runs_root.resolve()
    context.assert_write_path(selected_runs)
    model = RuntimeProfile(profile_id=profile_id, runs_root=selected_runs)
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        with destination.open("x", encoding="utf-8", newline="\n") as handle:
            yaml.safe_dump(
                model.model_dump(mode="json", exclude_none=True),
                handle,
                allow_unicode=True,
                sort_keys=False,
            )
    except FileExistsError as error:
        raise ConfigurationError(f"Runtime profile 已存在，禁止覆盖: {destination}") from error
    return destination


def load_runtime_profile(path: Path | None = None) -> LoadedRuntimeProfile:
    selected = _latest_profile_path(resolve_runtime_profile_path(path).resolve())
    try:
        raw = yaml.safe_load(selected.read_text(encoding="utf-8"))
        profile = RuntimeProfile.model_validate(raw)
    except (OSError, UnicodeDecodeError, yaml.YAMLError, ValidationError) as error:
        raise ConfigurationError(f"Runtime profile 无法读取: {selected}: {error}") from error
    receipt = WorkspaceContext.discover(selected.parent).runtime_root / "state/runtime-link.json"
    if profile.runtime_link_source is not None and not receipt.is_file():
        raise ConfigurationError("linked runtime profile 缺少 receipt，拒绝使用")
    if receipt.is_file():
        from .runtime_link import verify_runtime_link

        verified = verify_runtime_link(receipt)
        if (
            profile.runtime_link_source != verified.source_runtime
            or profile.runtime_linked_at != verified.linked_at
        ):
            raise ConfigurationError("runtime profile 与最新 link receipt identity 不一致")
    if profile.backends.openfold3_af3_jax is not None:
        from .runtime_components import verify_openfold3_component

        component = verify_openfold3_component()
        runtime = profile.backends.openfold3_af3_jax
        if (
            runtime.environment_lock_sha256 != component.environment_lock_sha256
            or runtime.converted_weight_sha256
            != component.converted_weight_sha256
            or runtime.runner_commit != component.runner_commit
        ):
            raise ConfigurationError("runtime profile 与 OpenFold3 component identity 不一致")
    return LoadedRuntimeProfile(
        path=selected,
        profile=profile,
        identity=RuntimeProfileRef(
            profile_id=profile.profile_id,
            sha256=sha256_file(selected),
        ),
    )
