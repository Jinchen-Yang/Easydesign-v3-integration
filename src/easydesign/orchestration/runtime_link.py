"""Read-only linkage to an already verified EasyDesign scientific runtime."""

from __future__ import annotations

import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

import yaml  # type: ignore[import-untyped]
from pydantic import BaseModel, ConfigDict

from easydesign.core import ConfigurationError, sha256_file
from easydesign.orchestration.task_tracking import (
    atomic_dump_runtime_model,
    load_latest_runtime_model,
)
from easydesign.workspace_context import WorkspaceContext

from .profile import (
    BoltzGenRuntime,
    ProtenixV2Runtime,
    PyMOLPseRuntime,
    RuntimeBackends,
    RuntimeProfile,
    ScanNetEpitopeRuntime,
    TnpRuntime,
)

SCIENCE_ENVIRONMENTS = (
    "pymol-pse",
    "protenix-v2",
    "scannet-epitope",
    "boltzgen",
    "tnp",
)
REQUIRED_ASSETS = (
    "protenix-v2-checkpoint",
    "protenix-ccd-components",
    "protenix-ccd-rdkit-cache",
    "protenix-pdb-clusters",
    "protenix-obsolete-releases",
    "scannet-code-and-epitope-models",
    "boltzgen-inference-molecule-dataset",
    "boltzgen-design-diverse-checkpoint",
    "boltzgen-design-adherence-checkpoint",
    "boltzgen-inverse-fold-checkpoint",
    "boltzgen-folding-checkpoint",
    "boltzgen-affinity-checkpoint",
    "boltzgen-source-a3149cf",
    "tnp-source-29dcac72",
)


class _EnvironmentRecord(BaseModel):
    model_config = ConfigDict(extra="allow")

    environment_id: str
    lock_sha256: str
    relative_prefix: Path
    status: str
    package_inventory: Path | None = None
    package_inventory_sha256: str | None = None


class _AssetRecord(BaseModel):
    model_config = ConfigDict(extra="allow")

    asset_id: str
    relative_path: Path
    status: str
    sha256: str | None = None
    revision: str | None = None
    size_bytes: int | None = None


class LinkedEnvironment(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    environment_id: str
    record_revision: str
    record_sha256: str
    lock_sha256: str
    prefix: Path
    inventory: Path
    inventory_sha256: str


class LinkedAsset(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    asset_id: str
    record_revision: str
    record_sha256: str
    path: Path
    kind: Literal["file", "git"]
    sha256: str | None = None
    revision: str | None = None
    size_bytes: int | None = None
    mtime_ns: int


class RuntimeLinkReceipt(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["0.1"] = "0.1"
    source_runtime: Path
    linked_at: datetime
    environment_registry_sha256: str
    asset_registry_sha256: str
    environment_registry_tip: str
    environment_registry_tip_sha256: str
    asset_registry_tip: str
    asset_registry_tip_sha256: str
    environments: tuple[LinkedEnvironment, ...]
    assets: tuple[LinkedAsset, ...]


class RuntimeLinkResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    source_runtime: Path
    receipt: Path
    profile: Path
    environment_count: int
    asset_count: int


def _resolve_source_path(source_runtime: Path, relative: Path) -> Path:
    candidate = (source_runtime.parent / relative).resolve(strict=True)
    if not candidate.is_relative_to(source_runtime):
        raise ConfigurationError(f"共享 runtime 记录逃出只读边界: {relative}")
    return candidate


def _registry_records(
    root: Path,
    model_type: type[_EnvironmentRecord] | type[_AssetRecord],
    key: str,
) -> tuple[dict[str, tuple[BaseModel, Path]], Path]:
    revisions = sorted(root.glob("revision-*.json"))
    if not revisions:
        raise ConfigurationError(f"共享 registry 没有 revision: {root}")
    records: dict[str, tuple[BaseModel, Path]] = {}
    for path in revisions:
        try:
            model = model_type.model_validate_json(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            raise ConfigurationError(f"共享 registry revision 损坏: {path}") from error
        records[str(getattr(model, key))] = (model, path)
    return records, revisions[-1]


def _expected_lock_sha(context: WorkspaceContext, environment_id: str) -> str:
    path = context.root / "environments/locks" / f"{environment_id}-linux-64.lock.json"
    if not path.is_file():
        raise ConfigurationError(f"local 分支缺少环境 lock: {path}")
    return sha256_file(path)


def _git_head(path: Path) -> str:
    completed = subprocess.run(
        ["git", "-C", str(path), "rev-parse", "HEAD"],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        raise ConfigurationError(f"Git 资产无法验证 revision: {path}")
    return completed.stdout.strip()


def _write_profile_revision(context: WorkspaceContext, model: RuntimeProfile) -> Path:
    base = context.profile_path
    if not base.exists():
        destination = base
    else:
        revision_root = base.with_name(f"{base.name}.revisions")
        revision_root.mkdir(parents=True, exist_ok=True)
        revisions = sorted(revision_root.glob("revision-*.yaml"))
        number = len(revisions) + 1
        destination = revision_root / f"revision-{number:06d}.yaml"
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("x", encoding="utf-8", newline="\n") as handle:
        yaml.safe_dump(
            model.model_dump(mode="json", exclude_none=True),
            handle,
            allow_unicode=True,
            sort_keys=False,
        )
    return destination


def _asset_path(assets: dict[str, LinkedAsset], asset_id: str) -> Path:
    try:
        return assets[asset_id].path
    except KeyError as error:
        raise ConfigurationError(f"共享 runtime 缺少资产: {asset_id}") from error


def _profile(context: WorkspaceContext, receipt: RuntimeLinkReceipt) -> RuntimeProfile:
    from .runtime_components import active_openfold3_runtime

    envs = {item.environment_id: item.prefix for item in receipt.environments}
    assets = {item.asset_id: item for item in receipt.assets}
    protenix_prefix = envs["protenix-v2"]
    cuda_home = protenix_prefix / "targets/x86_64-linux"
    cuda_include = cuda_home / "include"
    cuda_lib = cuda_home / "lib"
    cxx = protenix_prefix / "bin/x86_64-conda-linux-gnu-c++"
    cc = protenix_prefix / "bin/x86_64-conda-linux-gnu-cc"
    include_flags = f"-I{cuda_include} -isystem {protenix_prefix / 'include'}"
    library_flags = f"-L{cuda_lib} -L{cuda_lib / 'stubs'} -L{protenix_prefix / 'lib'}"
    protenix_environment = (
        ("CONDA_PREFIX", str(protenix_prefix)),
        ("CUDA_HOME", str(cuda_home)),
        ("CC", str(cc)),
        ("CXX", str(cxx)),
        ("CFLAGS", f"{include_flags} {library_flags}"),
        ("CPPFLAGS", f"{include_flags} {library_flags}"),
        ("CXXFLAGS", f"{include_flags} {library_flags}"),
        ("LDFLAGS", library_flags),
        ("LIBRARY_PATH", f"{cuda_lib}:{protenix_prefix / 'lib'}"),
        ("LD_LIBRARY_PATH", f"{cuda_lib}:{protenix_prefix / 'lib'}"),
        ("PATH", str(protenix_prefix / "nvvm/bin")),
        (
            "_CONDA_PYTHON_SYSCONFIGDATA_NAME",
            "_sysconfigdata_x86_64_conda_cos7_linux_gnu",
        ),
    )
    boltzgen = BoltzGenRuntime(
        executable=envs["boltzgen"] / "bin/boltzgen",
        repository_root=_asset_path(assets, "boltzgen-source-a3149cf"),
        cache_root=receipt.source_runtime / "models/boltzgen/huggingface",
        offline_mode=True,
    )
    return RuntimeProfile(
        profile_id="vscode-local-linked",
        runs_root=context.runs_root,
        runtime_link_source=receipt.source_runtime,
        runtime_linked_at=receipt.linked_at,
        backends=RuntimeBackends(
            protenix_v2=ProtenixV2Runtime(
                executable=protenix_prefix / "bin/protenix",
                model_root=receipt.source_runtime / "models/protenix-v2",
                model_checkpoint=_asset_path(assets, "protenix-v2-checkpoint"),
                extra_environment=protenix_environment,
            ),
            openfold3_af3_jax=active_openfold3_runtime(context),
            pymol_pse=PyMOLPseRuntime(
                python=envs["pymol-pse"] / "bin/python",
            ),
            scannet_epitope=ScanNetEpitopeRuntime(
                python=envs["scannet-epitope"] / "bin/python",
                repository_root=_asset_path(assets, "scannet-code-and-epitope-models"),
                execution_device="cpu",
            ),
            boltzgen_validation=boltzgen,
            boltzgen=boltzgen,
            tnp=TnpRuntime(
                python=envs["tnp"] / "bin/python",
                executable=_asset_path(assets, "tnp-source-29dcac72") / "bin/TNP",
                repository_root=_asset_path(assets, "tnp-source-29dcac72"),
            ),
        ),
    )


def link_runtime(source: Path) -> RuntimeLinkResult:
    """Verify a source runtime and append a local link/profile revision."""

    context = WorkspaceContext.discover()
    source_runtime = source.expanduser().resolve(strict=True)
    if not source_runtime.is_dir() or source_runtime == context.runtime_root:
        raise ConfigurationError("runtime link 必须指向另一个已安装 runtime 目录")
    if source_runtime in (context.projects_root, context.runs_root, context.archives_root):
        raise ConfigurationError("拒绝把项目或 run 数据目录作为 runtime source")
    environment_marker = source_runtime / "environment-registry.json"
    asset_marker = source_runtime / "asset-registry.json"
    for marker in (environment_marker, asset_marker):
        if not marker.is_file():
            raise ConfigurationError(f"共享 runtime 缺少 registry marker: {marker}")
        try:
            payload: Any = json.loads(marker.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise ConfigurationError(f"共享 runtime registry marker 损坏: {marker}") from error
        if not isinstance(payload, dict) or not payload.get("record_directory"):
            raise ConfigurationError(
                f"共享 runtime registry marker 缺少 record_directory: {marker}"
            )

    environment_records, environment_tip = _registry_records(
        source_runtime / "state/registries/environments",
        _EnvironmentRecord,
        "environment_id",
    )
    asset_records, asset_tip = _registry_records(
        source_runtime / "state/registries/assets",
        _AssetRecord,
        "asset_id",
    )
    linked_environments: list[LinkedEnvironment] = []
    for environment_id in SCIENCE_ENVIRONMENTS:
        try:
            raw, revision = environment_records[environment_id]
        except KeyError as error:
            raise ConfigurationError(f"共享 runtime 未登记环境: {environment_id}") from error
        environment_record = _EnvironmentRecord.model_validate(raw)
        if environment_record.status != "available":
            raise ConfigurationError(
                f"共享环境不可用: {environment_id}={environment_record.status}"
            )
        expected_lock = _expected_lock_sha(context, environment_id)
        if environment_record.lock_sha256 != expected_lock:
            raise ConfigurationError(
                f"共享环境 lock 与 local 分支不一致: {environment_id}"
            )
        if (
            environment_record.package_inventory is None
            or environment_record.package_inventory_sha256 is None
        ):
            raise ConfigurationError(f"共享环境缺少 inventory: {environment_id}")
        prefix = _resolve_source_path(source_runtime, environment_record.relative_prefix)
        inventory = _resolve_source_path(
            source_runtime, environment_record.package_inventory
        )
        actual_inventory_sha = sha256_file(inventory)
        if actual_inventory_sha != environment_record.package_inventory_sha256:
            raise ConfigurationError(f"共享环境 inventory SHA-256 不一致: {environment_id}")
        linked_environments.append(
            LinkedEnvironment(
                environment_id=environment_id,
                record_revision=revision.name,
                record_sha256=sha256_file(revision),
                lock_sha256=environment_record.lock_sha256,
                prefix=prefix,
                inventory=inventory,
                inventory_sha256=actual_inventory_sha,
            )
        )

    linked_assets: list[LinkedAsset] = []
    for asset_id in REQUIRED_ASSETS:
        try:
            raw, record_path = asset_records[asset_id]
        except KeyError as error:
            raise ConfigurationError(f"共享 runtime 未登记资产: {asset_id}") from error
        asset_record = _AssetRecord.model_validate(raw)
        if asset_record.status != "available":
            raise ConfigurationError(
                f"共享资产不可用: {asset_id}={asset_record.status}"
            )
        path = _resolve_source_path(source_runtime, asset_record.relative_path)
        stat = path.stat()
        if path.is_file():
            if asset_record.size_bytes is None or asset_record.sha256 is None:
                raise ConfigurationError(f"文件资产缺少 size/SHA-256: {asset_id}")
            if (
                stat.st_size != asset_record.size_bytes
                or sha256_file(path) != asset_record.sha256
            ):
                raise ConfigurationError(f"共享资产 identity 不一致: {asset_id}")
            kind: Literal["file", "git"] = "file"
        elif path.is_dir() and asset_record.revision is not None:
            if _git_head(path) != asset_record.revision:
                raise ConfigurationError(f"共享 Git 资产 revision 不一致: {asset_id}")
            kind = "git"
        else:
            raise ConfigurationError(f"共享资产类型无法验证: {asset_id}")
        linked_assets.append(
            LinkedAsset(
                asset_id=asset_id,
                record_revision=record_path.name,
                record_sha256=sha256_file(record_path),
                path=path,
                kind=kind,
                sha256=asset_record.sha256,
                revision=asset_record.revision,
                size_bytes=asset_record.size_bytes,
                mtime_ns=stat.st_mtime_ns,
            )
        )

    receipt = RuntimeLinkReceipt(
        source_runtime=source_runtime,
        linked_at=datetime.now(UTC),
        environment_registry_sha256=sha256_file(environment_marker),
        asset_registry_sha256=sha256_file(asset_marker),
        environment_registry_tip=environment_tip.name,
        environment_registry_tip_sha256=sha256_file(environment_tip),
        asset_registry_tip=asset_tip.name,
        asset_registry_tip_sha256=sha256_file(asset_tip),
        environments=tuple(linked_environments),
        assets=tuple(linked_assets),
    )
    profile_path = _write_profile_revision(context, _profile(context, receipt))
    receipt_path = context.runtime_root / "state/runtime-link.json"
    atomic_dump_runtime_model(receipt, receipt_path)
    return RuntimeLinkResult(
        source_runtime=source_runtime,
        receipt=receipt_path,
        profile=profile_path,
        environment_count=len(linked_environments),
        asset_count=len(linked_assets),
    )


def verify_runtime_link(receipt_path: Path | None = None) -> RuntimeLinkReceipt:
    """Fail closed when a linked registry, inventory, or asset identity changes."""

    context = WorkspaceContext.discover()
    selected = (
        context.runtime_root / "state/runtime-link.json"
        if receipt_path is None
        else receipt_path.resolve()
    )
    receipt = load_latest_runtime_model(selected, RuntimeLinkReceipt)
    source = receipt.source_runtime.resolve(strict=True)
    marker_checks = (
        (source / "environment-registry.json", receipt.environment_registry_sha256),
        (source / "asset-registry.json", receipt.asset_registry_sha256),
    )
    for path, expected in marker_checks:
        if sha256_file(path) != expected:
            raise ConfigurationError(f"共享 runtime registry identity 已变化: {path}")
    environment_records, environment_tip = _registry_records(
        source / "state/registries/environments",
        _EnvironmentRecord,
        "environment_id",
    )
    asset_records, asset_tip = _registry_records(
        source / "state/registries/assets",
        _AssetRecord,
        "asset_id",
    )
    if (
        environment_tip.name != receipt.environment_registry_tip
        or sha256_file(environment_tip) != receipt.environment_registry_tip_sha256
        or asset_tip.name != receipt.asset_registry_tip
        or sha256_file(asset_tip) != receipt.asset_registry_tip_sha256
    ):
        raise ConfigurationError("共享 runtime registry 已追加或改变；请重新执行 runtime link")
    for linked_environment in receipt.environments:
        raw, record_path = environment_records[linked_environment.environment_id]
        environment_record = _EnvironmentRecord.model_validate(raw)
        if (
            record_path.name != linked_environment.record_revision
            or sha256_file(record_path) != linked_environment.record_sha256
            or environment_record.status != "available"
            or environment_record.lock_sha256 != linked_environment.lock_sha256
            or not linked_environment.prefix.is_dir()
            or sha256_file(linked_environment.inventory)
            != linked_environment.inventory_sha256
        ):
            raise ConfigurationError(
                f"共享环境 identity 已变化: {linked_environment.environment_id}"
            )
    for linked_asset in receipt.assets:
        raw, record_path = asset_records[linked_asset.asset_id]
        asset_record = _AssetRecord.model_validate(raw)
        if (
            record_path.name != linked_asset.record_revision
            or sha256_file(record_path) != linked_asset.record_sha256
            or asset_record.status != "available"
            or not linked_asset.path.exists()
        ):
            raise ConfigurationError(
                f"共享资产 registry 已变化: {linked_asset.asset_id}"
            )
        stat = linked_asset.path.stat()
        if linked_asset.kind == "file":
            if stat.st_size != linked_asset.size_bytes:
                raise ConfigurationError(
                    f"共享资产大小已变化: {linked_asset.asset_id}"
                )
            if (
                stat.st_mtime_ns != linked_asset.mtime_ns
                and sha256_file(linked_asset.path) != linked_asset.sha256
            ):
                raise ConfigurationError(
                    f"共享资产 SHA-256 已变化: {linked_asset.asset_id}"
                )
        elif _git_head(linked_asset.path) != linked_asset.revision:
            raise ConfigurationError(
                f"共享 Git 资产 revision 已变化: {linked_asset.asset_id}"
            )
    return receipt


__all__ = [
    "RuntimeLinkReceipt",
    "RuntimeLinkResult",
    "link_runtime",
    "verify_runtime_link",
]
