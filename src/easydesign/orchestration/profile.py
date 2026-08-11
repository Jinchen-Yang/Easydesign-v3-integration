"""Explicit runtime profile whose scientific paths belong to this clone."""

from __future__ import annotations

from dataclasses import dataclass
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

    release_id: str
    backend_id: Literal["openfold3-af3-jax"]
    backend_version: str
    model_id: Literal["of3-p2-155k"]
    adapter_contract_version: Literal["openfold3-af3-jax-cli-v1"]
    python: Path
    runner: Path
    model_root: Path
    converted_weight: Path
    cache_root: Path
    raw_checkpoint_sha256: str
    converted_weight_sha256: str
    release_manifest_sha256: str
    conversion_receipt_sha256: str
    wheel_sha256: str
    runner_commit: str
    runner_tree_sha256: str
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
        "release_manifest_sha256",
        "conversion_receipt_sha256",
        "wheel_sha256",
        "runner_tree_sha256",
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
    profile_id: str = Field(default="clone-local", pattern=r"^[a-z0-9][a-z0-9._-]*$")
    runs_root: Path
    backends: RuntimeBackends = RuntimeBackends()

    @field_validator("runs_root")
    @classmethod
    def require_absolute_runs_root(cls, value: Path) -> Path:
        if not value.is_absolute():
            raise ValueError("runs_root 必须是绝对路径")
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
    """Create the profile populated by this clone's setup/component activation."""

    destination = resolve_runtime_profile_path(path).resolve()
    context = WorkspaceContext.discover(destination.parent)
    if not destination.is_relative_to(context.runtime_root):
        raise ConfigurationError("Runtime profile 必须位于当前 clone 的 runtime/ 内")
    selected_runs = context.runs_root if runs_root is None else runs_root.resolve()
    if selected_runs != context.runs_root:
        raise ConfigurationError("Runtime profile runs_root 必须是当前 clone 的 workspace/runs")
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


def _resolve_local_setup_backends(
    context: WorkspaceContext,
    current: RuntimeBackends,
) -> RuntimeBackends:
    """Resolve locally installed scientific components from immutable registries.

    Explicit profiles used by tests and advanced users remain valid until a
    component has a local registry record. Once a component is registered, its
    current lock and complete asset set become authoritative and fail closed.
    OpenFold3 remains independently activated by its verified component receipt.
    """

    from .runtime_setup import (
        expected_environment_lock_sha256,
        latest_asset_records,
        latest_environment_records,
    )

    environments = latest_environment_records(context)
    assets = latest_asset_records(context)
    if not environments and not assets:
        return current

    def available_prefix(environment_id: str) -> Path | None:
        record = environments.get(environment_id)
        if (
            record is None
            or record.status != "available"
            or record.lock_sha256
            != expected_environment_lock_sha256(context, environment_id)
        ):
            return None
        prefix = (context.root / record.relative_prefix).resolve()
        if prefix != context.runtime_root and not prefix.is_relative_to(
            context.runtime_root
        ):
            raise ConfigurationError(
                f"环境 registry 路径逃出当前 clone runtime: {environment_id}"
            )
        return prefix if prefix.is_dir() else None

    def available_asset(asset_id: str) -> Path | None:
        record = assets.get(asset_id)
        if record is None or record.status != "available":
            return None
        path = (context.root / record.relative_path).resolve()
        if path != context.runtime_root and not path.is_relative_to(
            context.runtime_root
        ):
            raise ConfigurationError(
                f"资产 registry 路径逃出当前 clone runtime: {asset_id}"
            )
        if not path.exists():
            return None
        if record.size_bytes is not None and path.is_file():
            try:
                if path.stat().st_size != record.size_bytes:
                    return None
            except OSError:
                return None
        return path

    def assets_ready(*asset_ids: str) -> bool:
        return all(available_asset(asset_id) is not None for asset_id in asset_ids)

    protenix_prefix = available_prefix("protenix-v2")
    protenix_checkpoint = available_asset("protenix-v2-checkpoint")
    protenix = (
        ProtenixV2Runtime(
            executable=protenix_prefix / "bin/protenix",
            model_root=context.runtime_root / "models/protenix-v2",
            model_checkpoint=protenix_checkpoint,
        )
        if protenix_prefix is not None
        and protenix_checkpoint is not None
        and assets_ready(
            "protenix-v2-checkpoint",
            "protenix-ccd-components",
            "protenix-ccd-rdkit-cache",
            "protenix-pdb-clusters",
            "protenix-obsolete-releases",
        )
        else None
    )

    pymol_prefix = available_prefix("pymol-pse")
    pymol = (
        PyMOLPseRuntime(python=pymol_prefix / "bin/python")
        if pymol_prefix is not None
        else None
    )

    scannet_prefix = available_prefix("scannet-epitope")
    scannet_root = available_asset("scannet-code-and-epitope-models")
    scannet = (
        ScanNetEpitopeRuntime(
            python=scannet_prefix / "bin/python",
            repository_root=scannet_root,
            execution_device="cpu",
        )
        if scannet_prefix is not None
        and scannet_root is not None
        and assets_ready("scannet-code-and-epitope-models")
        else None
    )

    boltzgen_prefix = available_prefix("boltzgen")
    boltzgen_root = available_asset("boltzgen-source-a3149cf")
    boltzgen_validation_ready = assets_ready(
        "boltzgen-source-a3149cf",
        "boltzgen-inference-molecule-dataset",
    )
    boltzgen_ready = boltzgen_validation_ready and assets_ready(
        "boltzgen-design-diverse-checkpoint",
        "boltzgen-design-adherence-checkpoint",
        "boltzgen-inverse-fold-checkpoint",
        "boltzgen-folding-checkpoint",
        "boltzgen-affinity-checkpoint",
    )
    boltzgen_validation = (
        BoltzGenRuntime(
            executable=boltzgen_prefix / "bin/boltzgen",
            repository_root=boltzgen_root,
            cache_root=context.runtime_root / "models/boltzgen/huggingface",
        )
        if boltzgen_prefix is not None
        and boltzgen_root is not None
        and boltzgen_validation_ready
        else None
    )
    boltzgen = boltzgen_validation if boltzgen_ready else None

    tnp_prefix = available_prefix("tnp")
    tnp_root = available_asset("tnp-source-29dcac72")
    tnp = (
        TnpRuntime(
            python=tnp_prefix / "bin/python",
            executable=tnp_root / "bin/TNP",
            repository_root=tnp_root,
        )
        if tnp_prefix is not None
        and tnp_root is not None
        and assets_ready("tnp-source-29dcac72")
        else None
    )

    return RuntimeBackends(
        protenix_v2=(
            protenix if "protenix-v2" in environments else current.protenix_v2
        ),
        openfold3_af3_jax=current.openfold3_af3_jax,
        pymol_pse=(
            pymol if "pymol-pse" in environments else current.pymol_pse
        ),
        scannet_epitope=(
            scannet
            if "scannet-epitope" in environments
            else current.scannet_epitope
        ),
        boltzgen_validation=(
            boltzgen_validation
            if "boltzgen" in environments
            else current.boltzgen_validation
        ),
        boltzgen=(
            boltzgen if "boltzgen" in environments else current.boltzgen
        ),
        tnp=(
            tnp if "tnp" in environments else current.tnp
        ),
    )


def _require_clone_local_profile(
    context: WorkspaceContext,
    profile: RuntimeProfile,
) -> None:
    if profile.runs_root.resolve(strict=False) != context.runs_root:
        raise ConfigurationError("Runtime profile runs_root 不属于当前 clone")
    runtime_root = context.runtime_root
    for backend_name in RuntimeBackends.model_fields:
        backend = getattr(profile.backends, backend_name)
        if backend is None:
            continue
        for field_name in type(backend).model_fields:
            value = getattr(backend, field_name)
            if not isinstance(value, Path):
                continue
            resolved = value.resolve(strict=False)
            if resolved != runtime_root and not resolved.is_relative_to(runtime_root):
                raise ConfigurationError(
                    "Runtime profile backend 路径逃出当前 clone runtime: "
                    f"{backend_name}.{field_name}={resolved}"
                )


def _load_runtime_profile_exact(selected: Path) -> LoadedRuntimeProfile:
    try:
        raw = yaml.safe_load(selected.read_text(encoding="utf-8"))
        profile = RuntimeProfile.model_validate(raw)
    except (OSError, UnicodeDecodeError, yaml.YAMLError, ValidationError) as error:
        raise ConfigurationError(f"Runtime profile 无法读取: {selected}: {error}") from error
    context = WorkspaceContext.discover(selected.parent)
    if not selected.is_relative_to(context.runtime_root):
        raise ConfigurationError("Runtime profile 必须位于当前 clone 的 runtime/ 内")
    _require_clone_local_profile(context, profile)
    if profile.backends.openfold3_af3_jax is not None:
        from .runtime_components import verify_openfold3_component

        component = verify_openfold3_component(
            context,
            release_id=profile.backends.openfold3_af3_jax.release_id,
        )
        runtime = profile.backends.openfold3_af3_jax
        if (
            runtime.release_manifest_sha256 != component.release_manifest_sha256
            or runtime.backend_version != component.backend_version
            or runtime.model_id != component.model_id
            or runtime.environment_lock_sha256 != component.environment_lock_sha256
            or runtime.converted_weight_sha256
            != component.converted_weight_sha256
            or runtime.runner_commit != component.runner_commit
            or runtime.runner_tree_sha256 != component.runner_tree_sha256
        ):
            raise ConfigurationError("runtime profile 与 OpenFold3 component identity 不一致")
    profile = profile.model_copy(
        update={
            "backends": _resolve_local_setup_backends(context, profile.backends),
        }
    )
    _require_clone_local_profile(context, profile)
    openfold3 = profile.backends.openfold3_af3_jax
    release_identities = (
        {}
        if openfold3 is None
        else {
            "openfold3-af3-jax": {
                "release_id": openfold3.release_id,
                "backend_id": openfold3.backend_id,
                "backend_version": openfold3.backend_version,
                "model_id": openfold3.model_id,
                "adapter_contract_version": openfold3.adapter_contract_version,
                "release_manifest_sha256": openfold3.release_manifest_sha256,
                "conversion_receipt_sha256": openfold3.conversion_receipt_sha256,
                "raw_checkpoint_sha256": openfold3.raw_checkpoint_sha256,
                "converted_weight_sha256": openfold3.converted_weight_sha256,
                "wheel_sha256": openfold3.wheel_sha256,
                "environment_lock_sha256": openfold3.environment_lock_sha256,
                "runner_commit": openfold3.runner_commit,
                "runner_tree_sha256": openfold3.runner_tree_sha256,
            }
        }
    )
    return LoadedRuntimeProfile(
        path=selected,
        profile=profile,
        identity=RuntimeProfileRef(
            profile_id=profile.profile_id,
            sha256=sha256_file(selected),
            release_identities=release_identities,
        ),
    )


def load_runtime_profile(path: Path | None = None) -> LoadedRuntimeProfile:
    selected = _latest_profile_path(resolve_runtime_profile_path(path).resolve())
    return _load_runtime_profile_exact(selected)


def load_runtime_profile_by_identity(
    identity: RuntimeProfileRef,
    path: Path | None = None,
) -> LoadedRuntimeProfile:
    """Resolve an append-only profile revision by its run-frozen content hash."""

    base = resolve_runtime_profile_path(path).resolve()
    revision_root = base.with_name(f"{base.name}.revisions")
    candidates = ([base] if base.is_file() else []) + sorted(
        revision_root.glob("revision-*.yaml")
    )
    matches = [candidate for candidate in candidates if sha256_file(candidate) == identity.sha256]
    if len(matches) != 1:
        raise ConfigurationError(
            "run 冻结的 runtime profile revision 不存在；拒绝改用当前 active profile: "
            f"{identity.sha256}"
        )
    loaded = _load_runtime_profile_exact(matches[0])
    if loaded.identity != identity:
        raise ConfigurationError("runtime profile identity 与 run 冻结值不一致")
    return loaded
