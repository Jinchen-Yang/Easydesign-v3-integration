"""跨平台、显式且不进入 run artifact 的本机 runtime profile。"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import yaml  # type: ignore[import-untyped]
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
)

from easydesign.core import ConfigurationError, RuntimeProfileRef, sha256_file
from easydesign.core.artifacts import ID_PATTERN
from easydesign.workspace_context import WorkspaceContext

from .runtime_setup import (
    expected_environment_lock_sha256,
    latest_asset_records,
    latest_environment_records,
)

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


class SshRemoteRuntime(BaseModel):
    """Deployment-only SSH control plane for running EasyDesign on another host."""

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        str_strip_whitespace=True,
    )

    host: str = Field(pattern=r"^[A-Za-z0-9.-]+$")
    user: str = Field(default="root", pattern=r"^[A-Za-z0-9._-]+$")
    port: int = Field(default=22, ge=1, le=65535)
    identity_file: Path
    known_hosts_file: Path = Path("/root/.ssh/known_hosts")
    ssh_executable: Path = Path("/usr/bin/ssh")
    rsync_executable: Path = Path("/usr/bin/rsync")
    remote_work_root: Path
    remote_runs_root: Path
    remote_easydesign_executable: Path
    remote_profile: Path
    launcher: Literal["systemd-run"] = "systemd-run"
    connect_timeout_seconds: int = Field(default=15, ge=1, le=120)

    @field_validator(
        "identity_file",
        "known_hosts_file",
        "ssh_executable",
        "rsync_executable",
        "remote_work_root",
        "remote_runs_root",
        "remote_easydesign_executable",
        "remote_profile",
    )
    @classmethod
    def require_absolute_path(cls, value: Path) -> Path:
        if not value.is_absolute():
            raise ValueError("SSH remote runtime 路径必须是绝对路径")
        return value


class RuntimeBackends(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    protenix_v2: ProtenixV2Runtime | None = None
    pymol_pse: PyMOLPseRuntime | None = None
    scannet_epitope: ScanNetEpitopeRuntime | None = None
    boltzgen_validation: BoltzGenRuntime | None = None
    boltzgen: BoltzGenRuntime | None = None
    tnp: TnpRuntime | None = None


class RuntimeProfile(BaseModel):
    """只保存机器部署信息；科学参数仍属于 easydesign.yaml。"""

    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    schema_version: str = Field(default="0.1", pattern=r"^0\.1$")
    profile_id: str = Field(default="local", pattern=ID_PATTERN)
    runs_root: Path | None = None
    backends: RuntimeBackends = RuntimeBackends()
    remote_executors: dict[str, SshRemoteRuntime] = Field(default_factory=dict)

    @field_validator("runs_root")
    @classmethod
    def require_absolute_runs_root(cls, value: Path | None) -> Path | None:
        if value is not None and not value.is_absolute():
            raise ValueError("runs_root 必须是绝对路径")
        return value


class WorkspaceBackendBinding(BaseModel):
    """Portable backend identity resolved through workspace registries."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    environment_id: str = Field(pattern=ID_PATTERN)
    asset_ids: tuple[str, ...] = ()


class WorkspaceRuntimeBackends(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    protenix_v2: WorkspaceBackendBinding | None = None
    pymol_pse: WorkspaceBackendBinding | None = None
    scannet_epitope: WorkspaceBackendBinding | None = None
    boltzgen: WorkspaceBackendBinding | None = None
    tnp: WorkspaceBackendBinding | None = None


class WorkspaceRuntimeProfile(BaseModel):
    """Schema 0.2 stores only workspace-relative roots and stable IDs."""

    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    schema_version: str = Field(default="0.2", pattern=r"^0\.2$")
    profile_id: str = Field(default="workspace-local", pattern=ID_PATTERN)
    runs_root: Path = Path("workspace/runs")
    projects_root: Path = Path("workspace/projects")
    backend_bindings: WorkspaceRuntimeBackends = WorkspaceRuntimeBackends()
    remote_executors: dict[str, SshRemoteRuntime] = Field(default_factory=dict)

    @field_validator("runs_root", "projects_root")
    @classmethod
    def require_workspace_relative(cls, value: Path) -> Path:
        if value.is_absolute() or ".." in value.parts:
            raise ValueError("schema 0.2 本地路径必须是工作区内相对路径")
        return value

    @field_validator("remote_executors")
    @classmethod
    def validate_remote_executor_ids(
        cls,
        value: dict[str, SshRemoteRuntime],
    ) -> dict[str, SshRemoteRuntime]:
        if any(re.fullmatch(ID_PATTERN, executor_id) is None for executor_id in value):
            raise ValueError("remote executor ID 不符合稳定 ID 规则")
        return value


@dataclass(frozen=True, slots=True)
class LoadedRuntimeProfile:
    path: Path
    profile: RuntimeProfile
    identity: RuntimeProfileRef
    portable_profile: WorkspaceRuntimeProfile | None = None


def default_workspace_backend_bindings() -> WorkspaceRuntimeBackends:
    """Return the complete repository-local backend dependency declaration."""

    return WorkspaceRuntimeBackends(
        protenix_v2=WorkspaceBackendBinding(
            environment_id="protenix-v2",
            asset_ids=(
                "protenix-v2-checkpoint",
                "protenix-ccd-components",
                "protenix-ccd-rdkit-cache",
                "protenix-pdb-clusters",
                "protenix-obsolete-releases",
            ),
        ),
        pymol_pse=WorkspaceBackendBinding(environment_id="pymol-pse"),
        scannet_epitope=WorkspaceBackendBinding(
            environment_id="scannet-epitope",
            asset_ids=("scannet-code-and-epitope-models",),
        ),
        boltzgen=WorkspaceBackendBinding(
            environment_id="boltzgen",
            asset_ids=(
                "boltzgen-inference-molecule-dataset",
                "boltzgen-design-diverse-checkpoint",
                "boltzgen-design-adherence-checkpoint",
                "boltzgen-inverse-fold-checkpoint",
                "boltzgen-folding-checkpoint",
                "boltzgen-affinity-checkpoint",
                "boltzgen-source-a3149cf",
            ),
        ),
        tnp=WorkspaceBackendBinding(
            environment_id="tnp",
            asset_ids=("tnp-source-29dcac72",),
        ),
    )


def default_runtime_profile_path() -> Path:
    """Return the current repository's profile; never use a user-global path."""

    return WorkspaceContext.discover().profile_path


def resolve_runtime_profile_path(explicit_path: Path | None = None) -> Path:
    """Resolve an explicit migration path or the repository-local profile."""

    if explicit_path is not None:
        return explicit_path.expanduser()
    return default_runtime_profile_path()


def _profile_payload(profile: BaseModel) -> dict[str, object]:
    return profile.model_dump(mode="json", exclude_none=True)


def initialize_runtime_profile(
    path: Path | None = None,
    *,
    profile_id: str = "local",
    runs_root: Path | None = None,
) -> Path:
    """Exclusively create a repository-local schema 0.2 profile."""

    destination = resolve_runtime_profile_path(path).resolve()
    context = WorkspaceContext.discover(destination.parent)
    if runs_root is not None:
        resolved_runs = runs_root.expanduser().resolve()
        try:
            relative_runs = resolved_runs.relative_to(context.root)
        except ValueError as error:
            raise ConfigurationError("schema 0.2 runs_root 必须位于当前工作区") from error
    else:
        relative_runs = context.declaration.runs_root
    profile = WorkspaceRuntimeProfile(
        profile_id=profile_id,
        runs_root=relative_runs,
        projects_root=context.declaration.projects_root,
        backend_bindings=default_workspace_backend_bindings(),
    )
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
    schema_version = raw.get("schema_version")
    try:
        portable: WorkspaceRuntimeProfile | None = None
        if schema_version == "0.2":
            portable = WorkspaceRuntimeProfile.model_validate(raw)
            context = WorkspaceContext.discover(resolved.parent)
            profile = _resolve_workspace_profile(context, portable)
        else:
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
        portable_profile=portable,
    )


def _available_prefix(
    context: WorkspaceContext,
    binding: WorkspaceBackendBinding | None,
) -> Path | None:
    if binding is None:
        return None
    record = latest_environment_records(context).get(binding.environment_id)
    if (
        record is None
        or record.status != "available"
        or record.lock_sha256
        != expected_environment_lock_sha256(context, binding.environment_id)
    ):
        return None
    prefix = (context.root / record.relative_prefix).resolve()
    context.assert_write_path(prefix)
    return prefix if prefix.is_dir() else None


def _available_asset(
    context: WorkspaceContext,
    asset_id: str,
) -> Path | None:
    record = latest_asset_records(context).get(asset_id)
    if record is None or record.status != "available":
        return None
    path = (context.root / record.relative_path).resolve()
    context.assert_write_path(path)
    if not path.exists():
        return None
    if record.size_bytes is not None and path.is_file():
        try:
            if path.stat().st_size != record.size_bytes:
                return None
        except OSError:
            return None
    return path


def _binding_assets_available(
    context: WorkspaceContext,
    binding: WorkspaceBackendBinding | None,
    *,
    required_asset_ids: frozenset[str],
) -> bool:
    """Require every declared backend asset before exposing an adapter.

    A workspace profile is a portable dependency declaration, not a hint.
    Exposing a backend after finding only its primary checkpoint would allow
    doctor and the UI to report a partially installed backend as usable.
    """

    if binding is None:
        return False
    declared = frozenset(binding.asset_ids)
    # Older schema-0.2 profiles remain immutable evidence when a newer
    # EasyDesign release adds a mandatory asset.  The current adapter contract
    # supplies those new requirements without rewriting the existing profile;
    # explicitly declared extra assets remain mandatory as well.
    effective_requirements = required_asset_ids | declared
    return all(
        _available_asset(context, asset_id) is not None
        for asset_id in effective_requirements
    )


def _resolve_workspace_profile(
    context: WorkspaceContext,
    portable: WorkspaceRuntimeProfile,
) -> RuntimeProfile:
    """Resolve IDs to absolute adapter paths at the application boundary."""

    bindings = portable.backend_bindings
    protenix_prefix = _available_prefix(context, bindings.protenix_v2)
    checkpoint = _available_asset(context, "protenix-v2-checkpoint")
    protenix_assets_ready = _binding_assets_available(
        context,
        bindings.protenix_v2,
        required_asset_ids=frozenset(
            {
                "protenix-v2-checkpoint",
                "protenix-ccd-components",
                "protenix-ccd-rdkit-cache",
                "protenix-pdb-clusters",
                "protenix-obsolete-releases",
            }
        ),
    )
    model_root = context.runtime_root / "models" / "protenix-v2"
    protenix = (
        ProtenixV2Runtime(
            executable=protenix_prefix / "bin" / "protenix",
            model_root=model_root,
            model_checkpoint=checkpoint,
        )
        if (
            protenix_prefix is not None
            and checkpoint is not None
            and protenix_assets_ready
        )
        else None
    )
    pymol_prefix = _available_prefix(context, bindings.pymol_pse)
    pymol = (
        PyMOLPseRuntime(python=pymol_prefix / "bin" / "python")
        if pymol_prefix is not None
        else None
    )
    scannet_prefix = _available_prefix(context, bindings.scannet_epitope)
    scannet_root = _available_asset(context, "scannet-code-and-epitope-models")
    scannet_assets_ready = _binding_assets_available(
        context,
        bindings.scannet_epitope,
        required_asset_ids=frozenset({"scannet-code-and-epitope-models"}),
    )
    scannet = (
        ScanNetEpitopeRuntime(
            python=scannet_prefix / "bin" / "python",
            repository_root=scannet_root,
            execution_device="cpu",
        )
        if (
            scannet_prefix is not None
            and scannet_root is not None
            and scannet_assets_ready
        )
        else None
    )
    boltzgen_prefix = _available_prefix(context, bindings.boltzgen)
    boltzgen_root = _available_asset(context, "boltzgen-source-a3149cf")
    molecule_archive = _available_asset(context, "boltzgen-inference-molecule-dataset")
    boltzgen_validation_assets_ready = _binding_assets_available(
        context,
        bindings.boltzgen,
        required_asset_ids=frozenset(
            {
                "boltzgen-source-a3149cf",
                "boltzgen-inference-molecule-dataset",
            }
        ),
    )
    boltzgen_assets_ready = _binding_assets_available(
        context,
        bindings.boltzgen,
        required_asset_ids=frozenset(
            {
                "boltzgen-source-a3149cf",
                "boltzgen-inference-molecule-dataset",
                "boltzgen-design-diverse-checkpoint",
                "boltzgen-design-adherence-checkpoint",
                "boltzgen-inverse-fold-checkpoint",
                "boltzgen-folding-checkpoint",
                "boltzgen-affinity-checkpoint",
            }
        ),
    )
    boltzgen_validation = (
        BoltzGenRuntime(
            executable=boltzgen_prefix / "bin" / "boltzgen",
            repository_root=boltzgen_root,
            cache_root=(
                context.runtime_root / "models" / "boltzgen" / "huggingface"
            ),
        )
        if (
            boltzgen_prefix is not None
            and boltzgen_root is not None
            and molecule_archive is not None
            and boltzgen_validation_assets_ready
        )
        else None
    )
    boltzgen = (
        boltzgen_validation
        if (
            boltzgen_validation is not None
            and boltzgen_assets_ready
        )
        else None
    )
    tnp_prefix = _available_prefix(context, bindings.tnp)
    tnp_root = _available_asset(context, "tnp-source-29dcac72")
    tnp_assets_ready = _binding_assets_available(
        context,
        bindings.tnp,
        required_asset_ids=frozenset({"tnp-source-29dcac72"}),
    )
    tnp = (
        TnpRuntime(
            python=tnp_prefix / "bin" / "python",
            executable=tnp_root / "bin" / "TNP",
            repository_root=tnp_root,
        )
        if tnp_prefix is not None and tnp_root is not None and tnp_assets_ready
        else None
    )
    runs_root = (context.root / portable.runs_root).resolve()
    context.assert_write_path(runs_root)
    return RuntimeProfile(
        profile_id=portable.profile_id,
        runs_root=runs_root,
        backends=RuntimeBackends(
            protenix_v2=protenix,
            pymol_pse=pymol,
            scannet_epitope=scannet,
            boltzgen_validation=boltzgen_validation,
            boltzgen=boltzgen,
            tnp=tnp,
        ),
        remote_executors=portable.remote_executors,
    )
