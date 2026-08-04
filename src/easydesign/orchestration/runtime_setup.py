"""Repository-local environment and model setup with append-only records."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import shutil
import ssl
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlparse
from uuid import uuid4

import httpx
import yaml  # type: ignore[import-untyped]
from pydantic import BaseModel, ConfigDict, ValidationError

from easydesign.core import ConfigurationError, sha256_file
from easydesign.workspace_context import WorkspaceContext

ENVIRONMENT_IDS = (
    "easydesign-core",
    "reporting-web",
    "pymol-pse",
    "protenix-v2",
    "scannet-epitope",
    "boltzgen",
    "tnp",
)
SCIENCE_ENVIRONMENT_IDS = (
    "pymol-pse",
    "protenix-v2",
    "scannet-epitope",
    "boltzgen",
    "tnp",
)
MINIMAL_ENVIRONMENT_IDS = ("easydesign-core", "reporting-web")
SETUP_COMPONENT_ENVIRONMENTS: dict[str, tuple[str, ...]] = {
    "core-ui": MINIMAL_ENVIRONMENT_IDS,
    "pymol-pse": ("pymol-pse",),
    "protenix-v2": ("protenix-v2",),
    "scannet-epitope": ("scannet-epitope",),
    "boltzgen": ("boltzgen",),
    "tnp": ("tnp",),
}
SETUP_COMPONENT_ASSETS: dict[str, tuple[str, ...]] = {
    "core-ui": (),
    "pymol-pse": (),
    "protenix-v2": (
        "protenix-v2-checkpoint",
        "protenix-ccd-components",
        "protenix-ccd-rdkit-cache",
        "protenix-pdb-clusters",
        "protenix-obsolete-releases",
    ),
    "scannet-epitope": ("scannet-code-and-epitope-models",),
    "boltzgen": (
        "boltzgen-inference-molecule-dataset",
        "boltzgen-design-diverse-checkpoint",
        "boltzgen-design-adherence-checkpoint",
        "boltzgen-inverse-fold-checkpoint",
        "boltzgen-folding-checkpoint",
        "boltzgen-affinity-checkpoint",
        "boltzgen-source-a3149cf",
    ),
    "tnp": ("tnp-source-29dcac72",),
}
SETUP_COMPONENT_IDS = tuple(SETUP_COMPONENT_ENVIRONMENTS)
GIB = 1024**3
SETUP_FREE_RESERVE_BYTES = 10 * GIB
SYSTEM_CA_BUNDLE = Path("/etc/ssl/certs/ca-certificates.crt")
DEFAULT_PIP_INDEX_URL = "https://pypi.org/simple"
SetupMode = Literal["minimal", "full", "component"]


class EnvironmentLock(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["0.2"] = "0.2"
    environment_id: str
    platform: Literal["linux-64"]
    conda_explicit: Path
    conda_explicit_sha256: str
    pip_requirements: Path | None = None
    pip_requirements_sha256: str | None = None
    install_workspace_package: bool = False
    python: str | None
    probe: tuple[str, ...]
    estimated_install_bytes: int
    lock_kind: Literal["resolved-package-set"] = "resolved-package-set"


class EnvironmentRecord(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["0.1"] = "0.1"
    environment_id: str
    lock_sha256: str
    relative_prefix: Path
    status: Literal["available", "failed", "unsupported-platform", "retired"]
    python_version: str | None = None
    probe_command: tuple[str, ...]
    probe_returncode: int | None = None
    probe_stdout: str = ""
    probe_stderr: str = ""
    package_inventory: Path | None = None
    package_inventory_sha256: str | None = None
    recorded_at: datetime
    message: str | None = None


class AssetDefinition(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    asset_id: str
    kind: Literal["file", "git"]
    source: str
    destination: Path
    sha256: str | None = None
    revision: str | None = None
    expected_size_bytes: int | None = None
    estimated_install_bytes: int
    license: str
    license_confirmation_required: bool = True


class AssetCatalog(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["0.1"] = "0.1"
    assets: tuple[AssetDefinition, ...]


class AssetRecord(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["0.1"] = "0.1"
    asset_id: str
    relative_path: Path
    status: Literal["available", "awaiting-approval", "failed"]
    sha256: str | None = None
    revision: str | None = None
    size_bytes: int | None = None
    license: str
    recorded_at: datetime
    message: str | None = None


class SetupSummary(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    workspace: Path
    mode: SetupMode
    component: str | None = None
    environments: tuple[EnvironmentRecord, ...]
    assets: tuple[AssetRecord, ...]
    ok: bool
    awaiting_approval: tuple[str, ...] = ()
    pip_index_url: str = DEFAULT_PIP_INDEX_URL


def validate_pip_index_url(value: str) -> str:
    """Accept an explicit HTTPS package index without credentials or secrets."""

    normalized = value.rstrip("/")
    parsed = urlparse(normalized)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise ConfigurationError(
            "Pip index 必须是无凭据、无 query/fragment 的 HTTPS URL"
        )
    return normalized


def _pip_reliability_arguments(python: Path) -> list[str]:
    """Use resumable downloads when the locked pip version supports them."""

    base = ["--timeout", "120", "--retries", "10"]
    completed = subprocess.run(
        [str(python), "-c", "import pip; print(pip.__version__)"],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        return base
    try:
        major_text, minor_text, *_ = completed.stdout.strip().split(".")
        version = (int(major_text), int(minor_text))
    except ValueError:
        return base
    if version >= (25, 2):
        base.extend(("--resume-retries", "10"))
    return base


def _setup_selection(
    context: WorkspaceContext,
    *,
    minimal: bool,
    component: str | None,
) -> tuple[SetupMode, tuple[str, ...], tuple[AssetDefinition, ...]]:
    if minimal and component is not None:
        raise ConfigurationError("--minimal 与 --component 不能同时使用")
    catalog = _load_assets(context)
    if component is None:
        if minimal:
            return "minimal", MINIMAL_ENVIRONMENT_IDS, ()
        return "full", ENVIRONMENT_IDS, catalog.assets
    if component not in SETUP_COMPONENT_ENVIRONMENTS:
        supported = ", ".join(SETUP_COMPONENT_IDS)
        raise ConfigurationError(
            f"未知安装组件: {component}；可用组件: {supported}"
        )
    definitions = {asset.asset_id: asset for asset in catalog.assets}
    asset_ids = SETUP_COMPONENT_ASSETS[component]
    missing = tuple(asset_id for asset_id in asset_ids if asset_id not in definitions)
    if missing:
        raise ConfigurationError(
            f"安装组件 {component} 引用了未登记资产: {', '.join(missing)}"
        )
    return (
        "component",
        SETUP_COMPONENT_ENVIRONMENTS[component],
        tuple(definitions[asset_id] for asset_id in asset_ids),
    )


def _load_lock(context: WorkspaceContext, environment_id: str) -> tuple[EnvironmentLock, Path]:
    path = (
        context.root
        / "environments"
        / "locks"
        / f"{environment_id}-linux-64.lock.json"
    )
    try:
        lock = EnvironmentLock.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValidationError) as error:
        raise ConfigurationError(f"环境 lock 无法读取: {path}") from error
    if lock.environment_id != environment_id:
        raise ConfigurationError(f"环境 lock ID 不一致: {path}")
    if (lock.pip_requirements is None) != (
        lock.pip_requirements_sha256 is None
    ):
        raise ConfigurationError(f"环境 pip lock 路径和 SHA 必须同时声明: {path}")
    return lock, path


def _verified_lock_input(
    context: WorkspaceContext,
    path: Path,
    expected_sha256: str,
    *,
    label: str,
) -> Path:
    resolved = (context.root / path).resolve(strict=True)
    try:
        resolved.relative_to(context.root)
    except ValueError as error:
        raise ConfigurationError(f"{label} 必须位于 EasyDesign 仓库内") from error
    actual = sha256_file(resolved)
    if actual != expected_sha256:
        raise ConfigurationError(
            f"{label} SHA-256 不一致: expected={expected_sha256}, actual={actual}"
        )
    return resolved


def _load_assets(context: WorkspaceContext) -> AssetCatalog:
    path = context.root / "configs" / "runtime-assets.yaml"
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        return AssetCatalog.model_validate(raw)
    except (OSError, yaml.YAMLError, ValidationError) as error:
        raise ConfigurationError(f"运行资产目录无法读取: {path}") from error


def _revision_path(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    revisions = sorted(root.glob("revision-*.json"))
    next_revision = 1
    if revisions:
        try:
            next_revision = int(revisions[-1].stem.split("-")[-1]) + 1
        except ValueError as error:
            raise ConfigurationError(f"注册表 revision 文件名损坏: {revisions[-1]}") from error
    return root / f"revision-{next_revision:06d}.json"


def _append_record(root: Path, payload: BaseModel) -> Path:
    path = _revision_path(root)
    with path.open("x", encoding="utf-8") as handle:
        handle.write(
            json.dumps(payload.model_dump(mode="json"), ensure_ascii=False, indent=2)
            + "\n"
        )
    return path


def latest_environment_records(context: WorkspaceContext) -> dict[str, EnvironmentRecord]:
    records: dict[str, EnvironmentRecord] = {}
    for path in sorted(context.environment_registry_root.glob("revision-*.json")):
        record = EnvironmentRecord.model_validate_json(path.read_text(encoding="utf-8"))
        records[record.environment_id] = record
    return records


def retire_environment(
    context: WorkspaceContext,
    environment_id: str,
    *,
    reason: str,
) -> EnvironmentRecord:
    """Append a retirement record without changing the environment directory."""

    if environment_id not in ENVIRONMENT_IDS:
        raise ConfigurationError(f"未知环境 ID: {environment_id}")
    normalized_reason = reason.strip()
    if not normalized_reason:
        raise ConfigurationError("环境 retirement reason 不能为空")
    current = latest_environment_records(context).get(environment_id)
    if current is None:
        raise ConfigurationError(f"环境没有可 retirement 的 registry 记录: {environment_id}")
    if current.status == "retired":
        return current
    retired = current.model_copy(
        update={
            "status": "retired",
            "recorded_at": datetime.now(tz=UTC),
            "message": normalized_reason,
        }
    )
    _append_record(context.environment_registry_root, retired)
    return retired


def latest_asset_records(context: WorkspaceContext) -> dict[str, AssetRecord]:
    records: dict[str, AssetRecord] = {}
    for path in sorted(context.asset_registry_root.glob("revision-*.json")):
        record = AssetRecord.model_validate_json(path.read_text(encoding="utf-8"))
        records[record.asset_id] = record
    return records


def expected_environment_lock_sha256(
    context: WorkspaceContext,
    environment_id: str,
) -> str:
    """Return the tracked lock identity required by the current source tree."""

    _lock, path = _load_lock(context, environment_id)
    return sha256_file(path)


def _conda_executable(explicit: Path | None = None) -> Path:
    if explicit is not None:
        selected = explicit.expanduser().resolve(strict=True)
    else:
        candidate = os.environ.get("EASYDESIGN_CONDA") or shutil.which("conda")
        if candidate is None:
            raise ConfigurationError(
                "未找到 Conda；请安装 Miniconda/Anaconda 或设置 EASYDESIGN_CONDA"
            )
        selected = Path(candidate).expanduser().resolve(strict=True)
    if not selected.is_file():
        raise ConfigurationError(f"Conda executable 不可用: {selected}")
    return selected


def _probe_executable(prefix: Path, executable: str) -> str:
    direct = prefix / "bin" / executable
    return str(direct)


def _normalized_environment_inventory(payload: dict[str, Any]) -> dict[str, Any]:
    """Hide only the mutable commit of this workspace's editable package.

    The dependency environment is lock-addressed, while EasyDesign itself is
    intentionally installed editable for controller development. ``pip
    freeze`` therefore embeds the current Git commit in its VCS URL even when
    every locked third-party package is unchanged. Code identity is recorded
    by run/release manifests, so inventory comparison normalizes that one
    workspace-owned line and keeps every other package strict.
    """

    normalized = dict(payload)
    freeze = payload.get("pip_freeze")
    if isinstance(freeze, (list, tuple)):
        normalized["pip_freeze"] = [
            "-e workspace://easydesign#egg=easydesign"
            if isinstance(line, str)
            and line.startswith("-e ")
            and line.casefold().endswith("#egg=easydesign")
            else line
            for line in freeze
        ]
    return normalized


def _environment_inventory(
    context: WorkspaceContext,
    *,
    environment_id: str,
    prefix: Path,
    lock_sha256: str,
) -> tuple[Path, str]:
    """Freeze the actual Conda and pip package set after installation."""

    conda_packages = []
    conda_meta = prefix / "conda-meta"
    if conda_meta.is_dir():
        for path in sorted(conda_meta.glob("*.json")):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as error:
                raise ConfigurationError(
                    f"Conda package metadata 损坏: {path}"
                ) from error
            conda_packages.append(
                {
                    "name": payload.get("name"),
                    "version": payload.get("version"),
                    "build": payload.get("build"),
                    "channel": payload.get("channel"),
                    "sha256": payload.get("sha256"),
                }
            )
    pip_freeze: tuple[str, ...] = ()
    python = prefix / "bin" / "python"
    if python.is_file():
        completed = subprocess.run(
            [str(python), "-m", "pip", "freeze", "--all"],
            cwd=context.root,
            env={**os.environ, **context.child_environment()},
            capture_output=True,
            text=True,
            check=False,
            timeout=300,
        )
        if completed.returncode == 0:
            pip_freeze = tuple(
                sorted(
                    line.strip()
                    for line in completed.stdout.splitlines()
                    if line.strip()
                )
            )
    payload = {
        "schema_version": "0.1",
        "environment_id": environment_id,
        "lock_sha256": lock_sha256,
        "relative_prefix": str(prefix.relative_to(context.root)),
        "conda_packages": conda_packages,
        "pip_freeze": pip_freeze,
    }
    inventory_root = context.runtime_root / "state" / "environment-inventories"
    inventory_root.mkdir(parents=True, exist_ok=True)
    path = inventory_root / f"{environment_id}-{lock_sha256[:12]}.json"
    encoded = (
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    )
    if path.exists():
        try:
            existing_payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise ConfigurationError(f"环境 inventory 损坏: {path}") from error
        if not isinstance(existing_payload, dict) or (
            _normalized_environment_inventory(existing_payload)
            != _normalized_environment_inventory(payload)
        ):
            raise ConfigurationError(
                f"环境 inventory 已存在但内容变化，拒绝覆盖: {path}"
            )
    else:
        with path.open("x", encoding="utf-8") as handle:
            handle.write(encoded)
    return path.relative_to(context.root), sha256_file(path)


def _probe_environment(
    context: WorkspaceContext,
    lock: EnvironmentLock,
    prefix: Path,
    lock_sha256: str,
) -> EnvironmentRecord:
    command = list(lock.probe)
    command[0] = _probe_executable(prefix, command[0])
    if not Path(command[0]).is_file():
        return EnvironmentRecord(
            environment_id=lock.environment_id,
            lock_sha256=lock_sha256,
            relative_prefix=prefix.relative_to(context.root),
            status="failed",
            probe_command=tuple(command),
            probe_stderr="probe executable 不存在",
            recorded_at=datetime.now(tz=UTC),
        )
    try:
        completed = subprocess.run(
            command,
            cwd=context.root,
            env={**os.environ, **context.child_environment()},
            capture_output=True,
            text=True,
            check=False,
            timeout=300,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        return EnvironmentRecord(
            environment_id=lock.environment_id,
            lock_sha256=lock_sha256,
            relative_prefix=prefix.relative_to(context.root),
            status="failed",
            probe_command=tuple(command),
            probe_stderr=str(error),
            recorded_at=datetime.now(tz=UTC),
        )
    python_version: str | None = None
    python = prefix / "bin" / "python"
    if python.is_file():
        version = subprocess.run(
            [str(python), "--version"],
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
        python_version = (version.stdout or version.stderr).strip()
    inventory_path, inventory_sha256 = _environment_inventory(
        context,
        environment_id=lock.environment_id,
        prefix=prefix,
        lock_sha256=lock_sha256,
    )
    return EnvironmentRecord(
        environment_id=lock.environment_id,
        lock_sha256=lock_sha256,
        relative_prefix=prefix.relative_to(context.root),
        status="available" if completed.returncode == 0 else "failed",
        python_version=python_version,
        probe_command=tuple(command),
        probe_returncode=completed.returncode,
        probe_stdout=completed.stdout[-4000:],
        probe_stderr=completed.stderr[-4000:],
        package_inventory=inventory_path,
        package_inventory_sha256=inventory_sha256,
        recorded_at=datetime.now(tz=UTC),
    )


def ensure_environment(
    context: WorkspaceContext,
    environment_id: str,
    *,
    conda_executable: Path | None = None,
    pip_index_url: str = DEFAULT_PIP_INDEX_URL,
) -> EnvironmentRecord:
    """Create one immutable lock-addressed environment and probe it."""

    if platform.system() != "Linux" and environment_id not in MINIMAL_ENVIRONMENT_IDS:
        lock, lock_path = _load_lock(context, environment_id)
        record = EnvironmentRecord(
            environment_id=environment_id,
            lock_sha256=sha256_file(lock_path),
            relative_prefix=Path("runtime") / "envs" / environment_id,
            status="unsupported-platform",
            probe_command=lock.probe,
            recorded_at=datetime.now(tz=UTC),
        )
        _append_record(context.environment_registry_root, record)
        return record
    context.ensure_layout()
    selected_pip_index = validate_pip_index_url(pip_index_url)
    lock, lock_path = _load_lock(context, environment_id)
    lock_sha256 = sha256_file(lock_path)
    conda_explicit = _verified_lock_input(
        context,
        lock.conda_explicit,
        lock.conda_explicit_sha256,
        label=f"{environment_id} Conda explicit lock",
    )
    pip_requirements = (
        _verified_lock_input(
            context,
            lock.pip_requirements,
            lock.pip_requirements_sha256,
            label=f"{environment_id} pip requirements lock",
        )
        if (
            lock.pip_requirements is not None
            and lock.pip_requirements_sha256 is not None
        )
        else None
    )
    prefix = context.runtime_root / "envs" / f"{environment_id}-{lock_sha256[:12]}"
    context.assert_write_path(prefix)
    if prefix.exists():
        existing = _probe_environment(context, lock, prefix, lock_sha256)
        if existing.status == "available":
            _append_record(context.environment_registry_root, existing)
            return existing
        context.quarantine(
            prefix,
            operation=f"setup-{environment_id}",
            reason="现有 lock-addressed 环境未通过探针；保留后重建",
        )
    if not prefix.exists():
        install_phase = "conda-create"
        command = [
            str(_conda_executable(conda_executable)),
            "create",
            "--yes",
            "--prefix",
            str(prefix),
            "--file",
            str(conda_explicit),
        ]
        completed = subprocess.run(
            command,
            cwd=context.root,
            env={**os.environ, **context.child_environment()},
            check=False,
        )
        if completed.returncode == 0 and pip_requirements is not None:
            install_phase = "pip-lock-install"
            pip_environment = {
                **os.environ,
                **context.child_environment(),
                "PIP_INDEX_URL": selected_pip_index,
            }
            completed = subprocess.run(
                [
                    str(prefix / "bin" / "python"),
                    "-m",
                    "pip",
                    "install",
                    "--no-deps",
                    "--no-build-isolation",
                    *_pip_reliability_arguments(prefix / "bin" / "python"),
                    "--requirement",
                    str(pip_requirements),
                ],
                cwd=context.root,
                env=pip_environment,
                check=False,
            )
        if completed.returncode == 0 and lock.install_workspace_package:
            install_phase = "workspace-package-install"
            completed = subprocess.run(
                [
                    str(prefix / "bin" / "python"),
                    "-m",
                    "pip",
                    "install",
                    "--no-deps",
                    "--no-build-isolation",
                    "--editable",
                    ".[dev,ui]",
                ],
                cwd=context.root,
                env={
                    **os.environ,
                    **context.child_environment(),
                    "PIP_INDEX_URL": selected_pip_index,
                },
                check=False,
            )
        if completed.returncode != 0:
            if prefix.exists():
                context.quarantine(
                    prefix,
                    operation=f"setup-{environment_id}",
                    reason=(
                        f"{install_phase} 返回 {completed.returncode}；"
                        "环境 staging 已保留"
                    ),
                )
            failure_message = f"{install_phase} 返回 {completed.returncode}"
            failed = EnvironmentRecord(
                environment_id=environment_id,
                lock_sha256=lock_sha256,
                relative_prefix=prefix.relative_to(context.root),
                status="failed",
                probe_command=lock.probe,
                probe_returncode=completed.returncode,
                probe_stderr=failure_message,
                recorded_at=datetime.now(tz=UTC),
            )
            _append_record(context.environment_registry_root, failed)
            return failed
    record = _probe_environment(context, lock, prefix, lock_sha256)
    _append_record(context.environment_registry_root, record)
    return record


def _download_file(
    context: WorkspaceContext,
    asset: AssetDefinition,
    destination: Path,
) -> tuple[str, int]:
    staging = context.runtime_root / "tmp" / f"asset-{asset.asset_id}-{uuid4().hex}"
    context.assert_write_path(staging)
    try:
        verify: ssl.SSLContext | bool = True
        if SYSTEM_CA_BUNDLE.is_file():
            verify = ssl.create_default_context(cafile=str(SYSTEM_CA_BUNDLE))
        with httpx.Client(
            follow_redirects=True,
            timeout=httpx.Timeout(1800.0, connect=30.0),
            verify=verify,
            trust_env=True,
        ) as client:
            with client.stream("GET", asset.source) as response:
                response.raise_for_status()
                digest = hashlib.sha256()
                size = 0
                with staging.open("xb") as handle:
                    for chunk in response.iter_bytes():
                        handle.write(chunk)
                        digest.update(chunk)
                        size += len(chunk)
        actual = digest.hexdigest()
        if (
            asset.expected_size_bytes is not None
            and size != asset.expected_size_bytes
        ):
            context.quarantine(
                staging,
                operation=f"asset-{asset.asset_id}",
                reason=(
                    "size mismatch: "
                    f"expected={asset.expected_size_bytes}, actual={size}"
                ),
            )
            raise ConfigurationError(f"资产大小不匹配: {asset.asset_id}")
        if asset.sha256 is not None and actual != asset.sha256:
            context.quarantine(
                staging,
                operation=f"asset-{asset.asset_id}",
                reason=f"SHA-256 mismatch: expected={asset.sha256}, actual={actual}",
            )
            raise ConfigurationError(f"资产 SHA-256 不匹配: {asset.asset_id}")
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            raise ConfigurationError(f"资产目标已存在，拒绝覆盖: {destination}")
        staging.rename(destination)
        return actual, size
    except Exception:
        if staging.exists():
            context.quarantine(
                staging,
                operation=f"asset-{asset.asset_id}",
                reason="下载或发布未完成",
            )
        raise


def _directory_content_sha256(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(
        item
        for item in root.rglob("*")
        if item.is_file() and ".git" not in item.relative_to(root).parts
    ):
        relative = path.relative_to(root).as_posix().encode("utf-8")
        digest.update(len(relative).to_bytes(8, "big"))
        digest.update(relative)
        file_hash = sha256_file(path).encode("ascii")
        digest.update(file_hash)
    return digest.hexdigest()


def _checkout_git(
    context: WorkspaceContext,
    asset: AssetDefinition,
    destination: Path,
) -> tuple[str, str, int]:
    if asset.revision is None:
        raise ConfigurationError(f"Git 资产缺少 revision: {asset.asset_id}")
    staging = context.runtime_root / "tmp" / f"asset-{asset.asset_id}-{uuid4().hex}"
    context.assert_write_path(staging)
    environment = {**os.environ, **context.child_environment()}
    try:
        initialize = subprocess.run(
            ["git", "init", "--quiet", str(staging)],
            cwd=context.root,
            env=environment,
            check=False,
        )
        if initialize.returncode != 0:
            raise ConfigurationError(f"Git 资产 init 失败: {asset.asset_id}")
        remote = subprocess.run(
            ["git", "-C", str(staging), "remote", "add", "origin", asset.source],
            cwd=context.root,
            env=environment,
            check=False,
        )
        if remote.returncode != 0:
            raise ConfigurationError(f"Git 资产 remote 失败: {asset.asset_id}")
        fetch = subprocess.run(
            [
                "git",
                "-C",
                str(staging),
                "fetch",
                "--depth",
                "1",
                "--no-tags",
                "origin",
                asset.revision,
            ],
            cwd=context.root,
            env=environment,
            check=False,
        )
        if fetch.returncode != 0:
            raise ConfigurationError(f"Git 资产 fetch 失败: {asset.asset_id}")
        checkout = subprocess.run(
            ["git", "-C", str(staging), "checkout", "--detach", "FETCH_HEAD"],
            env=environment,
            check=False,
        )
        if checkout.returncode != 0:
            raise ConfigurationError(f"Git 资产 revision 不可用: {asset.asset_id}")
        revision = subprocess.run(
            ["git", "-C", str(staging), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        if revision != asset.revision:
            raise ConfigurationError(f"Git 资产 commit 不一致: {asset.asset_id}")
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            raise ConfigurationError(f"资产目标已存在，拒绝覆盖: {destination}")
        staging.rename(destination)
        size = sum(
            path.stat().st_size
            for path in destination.rglob("*")
            if path.is_file()
        )
        return revision, _directory_content_sha256(destination), size
    except Exception:
        if staging.exists():
            context.quarantine(
                staging,
                operation=f"asset-{asset.asset_id}",
                reason="Git checkout 或发布未完成",
            )
        raise


def ensure_asset(
    context: WorkspaceContext,
    asset: AssetDefinition,
    *,
    accepted_license_ids: set[str],
) -> AssetRecord:
    context.ensure_layout()
    destination = context.runtime_root / "models" / asset.destination
    context.assert_write_path(destination)
    if destination.exists():
        actual_sha = (
            sha256_file(destination)
            if destination.is_file()
            else _directory_content_sha256(destination)
        )
        actual_revision = asset.revision
        if destination.is_dir() and asset.kind == "git":
            environment = {**os.environ, **context.child_environment()}
            revision_check = subprocess.run(
                ["git", "-C", str(destination), "rev-parse", "HEAD"],
                env=environment,
                capture_output=True,
                text=True,
                check=False,
                timeout=30,
            )
            clean_check = subprocess.run(
                ["git", "-C", str(destination), "status", "--porcelain"],
                env=environment,
                capture_output=True,
                text=True,
                check=False,
                timeout=30,
            )
            if (
                revision_check.returncode != 0
                or revision_check.stdout.strip() != asset.revision
                or clean_check.returncode != 0
                or clean_check.stdout.strip()
            ):
                record = AssetRecord(
                    asset_id=asset.asset_id,
                    relative_path=destination.relative_to(context.root),
                    status="failed",
                    sha256=actual_sha,
                    revision=(
                        revision_check.stdout.strip()
                        if revision_check.returncode == 0
                        else None
                    ),
                    size_bytes=sum(
                        p.stat().st_size
                        for p in destination.rglob("*")
                        if p.is_file()
                    ),
                    license=asset.license,
                    recorded_at=datetime.now(tz=UTC),
                    message="现有 Git 资产 revision 不一致或工作树不干净；未覆盖",
                )
                _append_record(context.asset_registry_root, record)
                return record
        if asset.sha256 is not None and actual_sha != asset.sha256:
            record = AssetRecord(
                asset_id=asset.asset_id,
                relative_path=destination.relative_to(context.root),
                status="failed",
                sha256=actual_sha,
                revision=asset.revision,
                size_bytes=destination.stat().st_size if destination.is_file() else None,
                license=asset.license,
                recorded_at=datetime.now(tz=UTC),
                message="现有资产 checksum 与目录声明不一致；未覆盖",
            )
            _append_record(context.asset_registry_root, record)
            return record
        if (
            asset.expected_size_bytes is not None
            and destination.is_file()
            and destination.stat().st_size != asset.expected_size_bytes
        ):
            record = AssetRecord(
                asset_id=asset.asset_id,
                relative_path=destination.relative_to(context.root),
                status="failed",
                sha256=actual_sha,
                revision=actual_revision,
                size_bytes=destination.stat().st_size,
                license=asset.license,
                recorded_at=datetime.now(tz=UTC),
                message="现有资产大小与目录声明不一致；未覆盖",
            )
            _append_record(context.asset_registry_root, record)
            return record
        record = AssetRecord(
            asset_id=asset.asset_id,
            relative_path=destination.relative_to(context.root),
            status="available",
            sha256=actual_sha,
            revision=actual_revision,
            size_bytes=(
                destination.stat().st_size
                if destination.is_file()
                else sum(p.stat().st_size for p in destination.rglob("*") if p.is_file())
            ),
            license=asset.license,
            recorded_at=datetime.now(tz=UTC),
            message="已验证并复用现有资产",
        )
        _append_record(context.asset_registry_root, record)
        return record
    if asset.license_confirmation_required and asset.asset_id not in accepted_license_ids:
        record = AssetRecord(
            asset_id=asset.asset_id,
            relative_path=destination.relative_to(context.root),
            status="awaiting-approval",
            sha256=asset.sha256,
            revision=asset.revision,
            license=asset.license,
            recorded_at=datetime.now(tz=UTC),
            message="下载前需要用户确认运行时许可",
        )
        _append_record(context.asset_registry_root, record)
        return record
    try:
        if asset.kind == "file":
            identity, size = _download_file(context, asset, destination)
            sha256 = identity
            revision = None
        else:
            revision, sha256, size = _checkout_git(context, asset, destination)
        record = AssetRecord(
            asset_id=asset.asset_id,
            relative_path=destination.relative_to(context.root),
            status="available",
            sha256=sha256,
            revision=revision,
            size_bytes=size,
            license=asset.license,
            recorded_at=datetime.now(tz=UTC),
        )
    except Exception as error:
        record = AssetRecord(
            asset_id=asset.asset_id,
            relative_path=destination.relative_to(context.root),
            status="failed",
            sha256=asset.sha256,
            revision=asset.revision,
            license=asset.license,
            recorded_at=datetime.now(tz=UTC),
            message=str(error),
        )
    _append_record(context.asset_registry_root, record)
    return record


def initialize_workspace_metadata(context: WorkspaceContext) -> None:
    """Create immutable workspace-local profile and registry descriptors."""

    from .profile import WorkspaceRuntimeProfile, default_workspace_backend_bindings

    context.ensure_layout()
    profile = context.profile_path
    if not profile.exists():
        portable_profile = WorkspaceRuntimeProfile(
            profile_id="workspace-local",
            runs_root=context.declaration.runs_root,
            projects_root=context.declaration.projects_root,
            backend_bindings=default_workspace_backend_bindings(),
        )
        with profile.open("x", encoding="utf-8") as handle:
            handle.write(
                yaml.safe_dump(
                    portable_profile.model_dump(mode="json", exclude_none=True),
                    allow_unicode=True,
                    sort_keys=False,
                )
            )
    environment_descriptor = context.runtime_root / "environment-registry.json"
    if not environment_descriptor.exists():
        with environment_descriptor.open("x", encoding="utf-8") as handle:
            handle.write(
                json.dumps(
                {
                    "schema_version": "0.1",
                    "record_directory": "state/registries/environments",
                    "selection": "highest-valid-revision-per-environment-id",
                },
                    indent=2,
                )
                + "\n"
            )
    asset_descriptor = context.runtime_root / "asset-registry.json"
    if not asset_descriptor.exists():
        with asset_descriptor.open("x", encoding="utf-8") as handle:
            handle.write(
                json.dumps(
                {
                    "schema_version": "0.1",
                    "catalog": "../configs/runtime-assets.yaml",
                    "record_directory": "state/registries/assets",
                    "selection": "highest-valid-revision-per-asset-id",
                },
                    indent=2,
                )
                + "\n"
            )


def setup_workspace(
    context: WorkspaceContext,
    *,
    minimal: bool,
    component: str | None = None,
    accepted_license_ids: set[str],
    conda_executable: Path | None = None,
    pip_index_url: str = DEFAULT_PIP_INDEX_URL,
) -> SetupSummary:
    selected_pip_index = validate_pip_index_url(pip_index_url)
    plan = setup_plan(context, minimal=minimal, component=component)
    disk = plan["disk"]
    if not disk["sufficient"]:
        raise ConfigurationError(
            "工作区所在磁盘空间不足；"
            f"增量安装预计峰值 {disk['incremental_peak_bytes']} bytes，"
            f"要求保留 {disk['reserve_bytes']} bytes，"
            f"当前可用 {disk['free_bytes']} bytes"
        )
    initialize_workspace_metadata(context)
    mode, selected, selected_assets = _setup_selection(
        context,
        minimal=minimal,
        component=component,
    )
    environment_records = tuple(
        ensure_environment(
            context,
            environment_id,
            conda_executable=conda_executable,
            pip_index_url=selected_pip_index,
        )
        for environment_id in selected
    )
    asset_records: tuple[AssetRecord, ...] = ()
    if selected_assets:
        asset_records = tuple(
            ensure_asset(
                context,
                asset,
                accepted_license_ids=accepted_license_ids,
            )
            for asset in selected_assets
        )
    awaiting = tuple(
        record.asset_id
        for record in asset_records
        if record.status == "awaiting-approval"
    )
    ok = all(record.status == "available" for record in environment_records) and all(
        record.status == "available" for record in asset_records
    )
    return SetupSummary(
        workspace=context.root,
        mode=mode,
        component=component,
        environments=environment_records,
        assets=asset_records,
        ok=ok,
        awaiting_approval=awaiting,
        pip_index_url=selected_pip_index,
    )


def setup_plan(
    context: WorkspaceContext,
    *,
    minimal: bool,
    component: str | None = None,
) -> dict[str, Any]:
    mode, selected, selected_assets = _setup_selection(
        context,
        minimal=minimal,
        component=component,
    )
    environments: list[dict[str, Any]] = []
    for environment_id in selected:
        lock, path = _load_lock(context, environment_id)
        _verified_lock_input(
            context,
            lock.conda_explicit,
            lock.conda_explicit_sha256,
            label=f"{environment_id} Conda explicit lock",
        )
        if (
            lock.pip_requirements is not None
            and lock.pip_requirements_sha256 is not None
        ):
            _verified_lock_input(
                context,
                lock.pip_requirements,
                lock.pip_requirements_sha256,
                label=f"{environment_id} pip requirements lock",
            )
        environments.append(
            {
                "environment_id": environment_id,
                "lock_sha256": sha256_file(path),
                "conda_explicit": str(lock.conda_explicit),
                "conda_explicit_sha256": lock.conda_explicit_sha256,
                "pip_requirements": (
                    None
                    if lock.pip_requirements is None
                    else str(lock.pip_requirements)
                ),
                "pip_requirements_sha256": lock.pip_requirements_sha256,
                "target": str(
                    Path("runtime")
                    / "envs"
                    / f"{environment_id}-{sha256_file(path)[:12]}"
                ),
                "estimated_install_bytes": lock.estimated_install_bytes,
                "already_present": (
                    context.runtime_root
                    / "envs"
                    / f"{environment_id}-{sha256_file(path)[:12]}"
                ).exists(),
                "lock_kind": lock.lock_kind,
            }
        )
    assets = []
    for asset in selected_assets:
        payload = asset.model_dump(mode="json")
        payload["target"] = str(
            Path("runtime") / "models" / asset.destination
        )
        payload["already_present"] = (
            context.runtime_root / "models" / asset.destination
        ).exists()
        assets.append(payload)
    pending_environment_bytes = sum(
        int(item["estimated_install_bytes"])
        for item in environments
        if not item["already_present"]
    )
    pending_asset_bytes = sum(
        int(item["estimated_install_bytes"])
        for item in assets
        if not item["already_present"]
    )
    pending_asset_sizes = [
        int(item["estimated_install_bytes"])
        for item in assets
        if not item["already_present"]
    ]
    # Environments are built before assets, and assets are staged one at a
    # time. Account for the retained package cache plus the largest single
    # asset staging copy instead of pretending every asset is duplicated at
    # the same time.
    environment_and_cache_bytes = pending_environment_bytes * 2
    asset_phase_bytes = (
        environment_and_cache_bytes
        + pending_asset_bytes
        + max(pending_asset_sizes, default=0)
    )
    incremental_peak_bytes = max(
        environment_and_cache_bytes,
        asset_phase_bytes,
    )
    disk_usage = shutil.disk_usage(context.root)
    # Deployment policy: keep a fixed post-install reserve. A percentage of
    # total disk made the same component require progressively more unrelated
    # free space as the data volume grew.
    reserve_bytes = SETUP_FREE_RESERVE_BYTES
    sufficient = disk_usage.free >= incremental_peak_bytes + reserve_bytes
    return {
        "workspace": str(context.root),
        "mode": mode,
        "component": component,
        "environments": environments,
        "assets": assets,
        "disk": {
            "device_path": str(context.root),
            "total_bytes": disk_usage.total,
            "free_bytes": disk_usage.free,
            "pending_environment_bytes": pending_environment_bytes,
            "pending_asset_bytes": pending_asset_bytes,
            "incremental_peak_bytes": incremental_peak_bytes,
            "reserve_bytes": reserve_bytes,
            "sufficient": sufficient,
        },
        "write_roots": ["runtime", "projects", "runs", "archives", ".git"],
        "protected_external_state": [
            "/etc/environment",
            "shell profiles",
            "Git global configuration",
            "system proxy",
            "base Conda",
        ],
    }


def environment_status(context: WorkspaceContext) -> dict[str, Any]:
    records = latest_environment_records(context)
    result = []
    for environment_id in ENVIRONMENT_IDS:
        lock, path = _load_lock(context, environment_id)
        lock_sha256 = sha256_file(path)
        record = records.get(environment_id)
        current = record is not None and record.lock_sha256 == lock_sha256
        result.append(
            {
                "environment_id": environment_id,
                "expected_lock_sha256": lock_sha256,
                "status": (
                    "not-installed"
                    if record is None
                    else record.status if current else "outdated"
                ),
                "current": (
                    None
                    if record is None
                    else record.model_dump(mode="json")
                ),
                "conda_explicit": str(lock.conda_explicit),
                "pip_requirements": (
                    None
                    if lock.pip_requirements is None
                    else str(lock.pip_requirements)
                ),
            }
        )
    return {"workspace": str(context.root), "environments": result}


def asset_status(context: WorkspaceContext) -> dict[str, Any]:
    records = latest_asset_records(context)
    catalog = _load_assets(context)
    result = []
    for asset in catalog.assets:
        record = records.get(asset.asset_id)
        result.append(
            {
                "asset_id": asset.asset_id,
                "license": asset.license,
                "license_confirmation_required": asset.license_confirmation_required,
                "status": "not-installed" if record is None else record.status,
                "current": (
                    None
                    if record is None
                    else record.model_dump(mode="json")
                ),
                "destination": str(Path("runtime") / "models" / asset.destination),
            }
        )
    return {"workspace": str(context.root), "assets": result}


def import_legacy_deployment(
    context: WorkspaceContext,
    *,
    profile_path: Path,
    environment_root: Path,
) -> Path:
    """Copy legacy evidence into runtime/migrations without mutating its source."""

    source_profile = profile_path.expanduser().resolve(strict=True)
    source_environments = environment_root.expanduser().resolve(strict=True)
    if not source_profile.is_file():
        raise ConfigurationError(f"旧 profile 不是文件: {source_profile}")
    if not source_environments.is_dir():
        raise ConfigurationError(f"旧环境根目录不可读: {source_environments}")
    context.ensure_layout()
    operation_id = (
        datetime.now(tz=UTC).strftime("%Y%m%dT%H%M%SZ")
        + f"-legacy-import-{uuid4().hex[:10]}"
    )
    destination = context.runtime_root / "migrations" / operation_id
    context.assert_write_path(destination)
    destination.mkdir(parents=True, exist_ok=False)
    profile_copy = destination / "legacy-profile.yaml"
    shutil.copy2(source_profile, profile_copy)
    environments = []
    for candidate in sorted(source_environments.iterdir()):
        if not candidate.is_dir():
            continue
        conda_history = candidate / "conda-meta" / "history"
        environments.append(
            {
                "name": candidate.name,
                "source_path": str(candidate),
                "conda_history_sha256": (
                    sha256_file(conda_history) if conda_history.is_file() else None
                ),
                "status": "evidence-only-rebuild-required",
            }
        )
    report = {
        "schema_version": "0.1",
        "operation_id": operation_id,
        "imported_at": datetime.now(tz=UTC).isoformat(),
        "legacy_profile": {
            "source_path": str(source_profile),
            "copied_path": str(profile_copy.relative_to(context.root)),
            "sha256": sha256_file(profile_copy),
        },
        "legacy_environment_root": str(source_environments),
        "environments": environments,
        "source_preservation": "unchanged",
        "next_action": "run easydesign setup to rebuild lock-addressed environments",
    }
    report_path = destination / "migration-report.json"
    with report_path.open("x", encoding="utf-8") as handle:
        handle.write(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    initialize_workspace_metadata(context)
    return report_path
