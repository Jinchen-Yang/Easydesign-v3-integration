"""Repository-local EasyDesign workspace discovery and write policy.

The workspace marker is the single deployment boundary.  Normal EasyDesign
operations may read explicitly selected external inputs, but all mutable local
state is rooted below one of the declared workspace write roots.
"""

from __future__ import annotations

import hashlib
import os
import shutil
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import yaml  # type: ignore[import-untyped]
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from easydesign.core import ConfigurationError, PathPolicyError
from easydesign.execution_scope import (
    EXECUTION_SCOPE_ENV,
    ExecutionScope,
    load_scope,
    publish_scope,
)
from easydesign.runtime_guard import (
    LOCAL_WRITE_ROOTS_ENV,
    install_python_startup_guard,
)

WORKSPACE_MARKER = "easydesign-workspace.yaml"
WORKSPACE_ENVIRONMENT_VARIABLE = "EASYDESIGN_WORKSPACE"
CODE_ROOT_ENVIRONMENT_VARIABLE = "EASYDESIGN_CODE_ROOT"
_ACTIVE_CONTEXT: ContextVar[WorkspaceContext | None] = ContextVar(
    "easydesign_execution_context", default=None
)
# The first package cache generation could contain SHA-prefixed Conda archive
# basenames produced by older installers. Conda scans every archive at startup,
# so a new generation must not inherit those structurally invalid entries.
CONDA_PACKAGE_CACHE_NAME = "conda-packages-v2"

INHERITED_INTERPRETER_ENVIRONMENT = frozenset(
    {
        "CONDA_DEFAULT_ENV",
        "CONDA_PREFIX",
        "CONDA_PROMPT_MODIFIER",
        "CONDA_PYTHON_EXE",
        "CONDA_SHLVL",
        "PYTHONHOME",
        "PYTHONPATH",
        "PYTHONSTARTUP",
        "PYTHONUSERBASE",
        "VIRTUAL_ENV",
        "_CE_CONDA",
        "_CE_M",
    }
)


class WorkspaceDeclaration(BaseModel):
    """Tracked declaration of the portable workspace layout."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: str = Field(default="0.1", pattern=r"^0\.1$")
    workspace_id: str = Field(default="easydesign-local")
    runtime_root: Path = Path("runtime")
    projects_root: Path = Path("workspace/projects")
    runs_root: Path = Path("workspace/runs")
    archives_root: Path = Path("workspace/archives")
    upload_warning_bytes: int = Field(default=1 * 1024**3, gt=0)
    upload_blocking_bytes: int = Field(default=5 * 1024**3, gt=0)

    def model_post_init(self, __context: Any) -> None:
        if self.upload_blocking_bytes <= self.upload_warning_bytes:
            raise ValueError("上传阻断阈值必须大于警告阈值")
        for value in (
            self.runtime_root,
            self.projects_root,
            self.runs_root,
            self.archives_root,
        ):
            if value.is_absolute() or ".." in value.parts:
                raise ValueError("工作区声明路径必须是仓库内相对路径")


@dataclass(frozen=True, slots=True)
class WorkspaceContext:
    """Resolved workspace roots shared by CLI, UI, caches and workers."""

    root: Path
    declaration_path: Path
    declaration: WorkspaceDeclaration
    execution_scope: ExecutionScope | None = None
    execution_scope_path: Path | None = None

    @property
    def shared_runtime_root(self) -> Path:
        return self._resolve_declared(self.declaration.runtime_root)

    def base_context(self) -> WorkspaceContext:
        return replace(self, execution_scope=None, execution_scope_path=None)

    @staticmethod
    def scope_active() -> bool:
        active = _ACTIVE_CONTEXT.get()
        return bool(
            (active is not None and active.execution_scope is not None)
            or os.environ.get(EXECUTION_SCOPE_ENV)
        )

    def with_execution_scope(self, scope: ExecutionScope) -> WorkspaceContext:
        if self.execution_scope is not None:
            raise PathPolicyError("An execution scope cannot publish another scope")
        path = publish_scope(
            root=self.root,
            runtime_root=self.shared_runtime_root,
            declaration_path=self.declaration_path,
            scope=scope,
        )
        return replace(self, execution_scope=scope, execution_scope_path=path)

    @contextmanager
    def activate(self) -> Iterator[WorkspaceContext]:
        token = _ACTIVE_CONTEXT.set(self)
        try:
            yield self
        finally:
            _ACTIVE_CONTEXT.reset(token)

    def _scoped(self, path: Path) -> Path:
        if self.execution_scope is None:
            return path
        scoped = path / "scopes" / self.execution_scope.scope_id
        if scoped.resolve() != scoped:
            raise PathPolicyError("Scoped data roots cannot contain symlinks")
        return scoped

    @property
    def runtime_root(self) -> Path:
        return self._scoped(self.shared_runtime_root)

    @property
    def projects_root(self) -> Path:
        return self._scoped(self._resolve_declared(self.declaration.projects_root))

    @property
    def runs_root(self) -> Path:
        return self._scoped(self._resolve_declared(self.declaration.runs_root))

    @property
    def archives_root(self) -> Path:
        return self._scoped(self._resolve_declared(self.declaration.archives_root))

    @property
    def profile_path(self) -> Path:
        return self.shared_runtime_root / "profile.yaml"

    @property
    def environment_registry_root(self) -> Path:
        return self.shared_runtime_root / "state" / "registries" / "environments"

    @property
    def asset_registry_root(self) -> Path:
        return self.shared_runtime_root / "state" / "registries" / "assets"

    @property
    def gpu_lease_root(self) -> Path:
        return self.shared_runtime_root / "state" / "gpu-leases"

    @property
    def msa_cache_root(self) -> Path:
        return self.runtime_root / "cache" / "msa-v1"

    @property
    def scientific_http_cache_root(self) -> Path:
        return self.runtime_root / "cache" / "scientific-http-v1"

    def _resolve_declared(self, value: Path) -> Path:
        resolved = (self.root / value).resolve()
        try:
            resolved.relative_to(self.root)
        except ValueError as error:
            raise PathPolicyError("工作区声明逃出仓库根目录") from error
        return resolved

    def ensure_layout(self) -> None:
        """Create declared roots and runtime subdirectories without overwriting."""

        # Resolve every root before creating anything, and revalidate on each call.
        runtime, projects, runs, archives = (
            self.runtime_root,
            self.projects_root,
            self.runs_root,
            self.archives_root,
        )
        directories = (
            runtime,
            runtime / "cache",
            runtime / "state",
            runtime / "logs",
            runtime / "tmp",
            runtime / "validation",
            runtime / "quarantine",
            runtime / "home",
            projects,
            runs,
            archives,
        )
        for directory in directories:
            directory.mkdir(parents=True, exist_ok=True)

    def write_roots(self) -> tuple[Path, ...]:
        """The controller-declared mutable roots for this context.

        Unscoped controllers own the four workspace roots; a scoped execution
        additionally receives the shared GPU-lease registry so the native
        runtime can acquire, heartbeat and release host devices.
        """
        roots: tuple[Path, ...] = (
            self.runtime_root,
            self.projects_root,
            self.runs_root,
            self.archives_root,
        )
        if self.execution_scope is not None:
            roots = (*roots, self.gpu_lease_root)
        return roots

    def assert_write_path(self, path: Path, *, allow_git: bool = False) -> Path:
        """Reject a mutable target outside the explicit workspace write roots."""

        target = path.expanduser().resolve(strict=False)
        roots: list[Path] = list(self.write_roots())
        if allow_git:
            if self.execution_scope is not None:
                raise PathPolicyError("Scoped workers cannot modify Git metadata")
            roots.append((self.root / ".git").resolve(strict=False))
        if not any(target == root or target.is_relative_to(root) for root in roots):
            raise PathPolicyError(f"拒绝写入 EasyDesign 工作区外路径: {target}")
        return target

    def require_write_path(self, path: Path, *, purpose: str) -> Path:
        """Resolve one mutable target and include its purpose in failures."""

        try:
            return self.assert_write_path(path)
        except PathPolicyError as error:
            raise PathPolicyError(f"{purpose}: {error}") from error

    def _short_tmp_alias(self) -> Path:
        """Expose owned runtime/tmp through a Unix-socket-safe short path."""

        target = (self.runtime_root / "tmp").resolve(strict=True)
        system_tmp = Path("/tmp")
        if not system_tmp.is_dir():
            raise PathPolicyError("本机缺少 /tmp，无法创建短路径运行时别名")
        identity = self.root if self.execution_scope is None else self.runtime_root
        digest = hashlib.sha256(str(identity).encode("utf-8")).hexdigest()[:16]
        alias = system_tmp / f"easydesign-{digest}"
        if not alias.is_symlink() and not alias.exists():
            try:
                alias.symlink_to(target, target_is_directory=True)
            except FileExistsError:
                pass
        if not alias.is_symlink():
            raise PathPolicyError(f"短路径运行时别名被非符号链接占用: {alias}")
        if alias.resolve(strict=False) != target:
            raise PathPolicyError(f"短路径运行时别名身份冲突: {alias}")
        return alias

    def child_environment(self) -> dict[str, str]:
        """Environment isolation applied only to EasyDesign child processes."""

        # Asset verification may use the unscoped read context, but any helper
        # process must retain the caller's execution confinement.
        if self.execution_scope is None:
            active = _ACTIVE_CONTEXT.get()
            if (
                active is not None
                and active.root == self.root
                and active.execution_scope is not None
            ):
                return active.child_environment()
            configured = os.environ.get(EXECUTION_SCOPE_ENV)
            if configured:
                path = Path(configured)
                scope = load_scope(
                    runtime_root=self.shared_runtime_root,
                    declaration_path=self.declaration_path,
                    path=path,
                )
                return replace(
                    self, execution_scope=scope, execution_scope_path=path
                ).child_environment()
        self.ensure_layout()
        cache = self.runtime_root / "cache"
        git_config = self._git_config_path()
        startup_root = install_python_startup_guard(self.runtime_root / "state")
        python_path = [startup_root]
        selected_code_root = os.environ.get(CODE_ROOT_ENVIRONMENT_VARIABLE)
        if selected_code_root:
            code_root = Path(selected_code_root).expanduser().resolve(strict=True)
            allowed_root = (self.shared_runtime_root / "tmp").resolve(strict=True)
            if not code_root.is_relative_to(allowed_root):
                raise PathPolicyError(f"{CODE_ROOT_ENVIRONMENT_VARIABLE} 必须位于 runtime/tmp 内")
            if not (
                (code_root / ".git").exists()
                and (code_root / "pyproject.toml").is_file()
                and (code_root / "src/easydesign/__init__.py").is_file()
            ):
                raise PathPolicyError(
                    f"{CODE_ROOT_ENVIRONMENT_VARIABLE} 不是完整 EasyDesign Git 工作树"
                )
            python_path.append(code_root / "src")
        values = {
            "HOME": str(self.runtime_root / "home"),
            "TMPDIR": str(self._short_tmp_alias()),
            "CONDA_PKGS_DIRS": str(cache / CONDA_PACKAGE_CACHE_NAME),
            "PIP_CACHE_DIR": str(cache / "pip"),
            "UV_CACHE_DIR": str(cache / "uv"),
            "PIP_CONFIG_FILE": os.devnull,
            "PIP_INDEX_URL": "https://pypi.org/simple",
            "PIP_DISABLE_PIP_VERSION_CHECK": "1",
            "PIP_ROOT_USER_ACTION": "ignore",
            "PYTHONNOUSERSITE": "1",
            "PYTHONDONTWRITEBYTECODE": "1",
            "XDG_CACHE_HOME": str(cache / "xdg"),
            "XDG_DATA_HOME": str(self.runtime_root / "state" / "xdg-data"),
            "XDG_STATE_HOME": str(self.runtime_root / "state" / "xdg-state"),
            "HF_HOME": str(cache / "huggingface"),
            "HUGGINGFACE_HUB_CACHE": str(cache / "huggingface" / "hub"),
            "TRANSFORMERS_CACHE": str(cache / "huggingface" / "transformers"),
            "TORCH_HOME": str(cache / "torch"),
            "TORCH_EXTENSIONS_DIR": str(cache / "torch-extensions"),
            "HF_HUB_OFFLINE": "1",
            "TRANSFORMERS_OFFLINE": "1",
            "COREPACK_HOME": str(cache / "corepack"),
            "PLAYWRIGHT_BROWSERS_PATH": str(cache / "playwright"),
            "NPM_CONFIG_CACHE": str(cache / "npm"),
            "GIT_CONFIG_GLOBAL": str(git_config),
            WORKSPACE_ENVIRONMENT_VARIABLE: str(self.root),
            LOCAL_WRITE_ROOTS_ENV: os.pathsep.join(str(path) for path in self.write_roots()),
            "PYTHONPATH": os.pathsep.join(str(path) for path in python_path),
        }
        if selected_code_root:
            # Keep an explicitly selected immutable release in grandchildren too.
            # Otherwise a scoped worker's next child silently imports the base tree.
            values[CODE_ROOT_ENVIRONMENT_VARIABLE] = str(code_root)
        if self.execution_scope is not None:
            if self.execution_scope_path is None:
                raise PathPolicyError("Execution scope was not published by the controller")
            self.gpu_lease_root.mkdir(parents=True, exist_ok=True)
            values[EXECUTION_SCOPE_ENV] = str(self.execution_scope_path)
            values["CUDA_VISIBLE_DEVICES"] = ",".join(str(d) for d in self.execution_scope.devices)
        system_ca = Path("/etc/ssl/certs/ca-certificates.crt")
        if system_ca.is_file():
            values.update(
                {
                    "REQUESTS_CA_BUNDLE": str(system_ca),
                    "PIP_CERT": str(system_ca),
                    "SSL_CERT_FILE": str(system_ca),
                    "NODE_EXTRA_CA_CERTS": str(system_ca),
                }
            )
        non_directory_values = {
            "GIT_CONFIG_GLOBAL",
            WORKSPACE_ENVIRONMENT_VARIABLE,
            "PIP_CONFIG_FILE",
            "PIP_INDEX_URL",
            "PIP_DISABLE_PIP_VERSION_CHECK",
            "PIP_ROOT_USER_ACTION",
            "PYTHONNOUSERSITE",
            "PYTHONDONTWRITEBYTECODE",
            "HF_HUB_OFFLINE",
            "TRANSFORMERS_OFFLINE",
            "REQUESTS_CA_BUNDLE",
            "PIP_CERT",
            "SSL_CERT_FILE",
            "NODE_EXTRA_CA_CERTS",
            LOCAL_WRITE_ROOTS_ENV,
            "PYTHONPATH",
            CODE_ROOT_ENVIRONMENT_VARIABLE,
            EXECUTION_SCOPE_ENV,
            "CUDA_VISIBLE_DEVICES",
        }
        for key, value in values.items():
            if key in non_directory_values:
                continue
            Path(value).mkdir(parents=True, exist_ok=True)
        return values

    def subprocess_environment(
        self,
        *,
        python_startup_guard: bool = True,
        environment_prefix: Path | None = None,
    ) -> dict[str, str]:
        """Build a complete child environment without host interpreter state."""

        environment = {
            key: value
            for key, value in os.environ.items()
            if key not in INHERITED_INTERPRETER_ENVIRONMENT
        }
        overrides = self.child_environment()
        if not python_startup_guard:
            overrides.pop("PYTHONPATH", None)
        environment.update(overrides)
        if environment_prefix is not None:
            prefix = environment_prefix.resolve()
            environment["PATH"] = os.pathsep.join(
                part
                for part in (
                    str(prefix / "bin"),
                    environment.get("PATH", ""),
                )
                if part
            )
            environment["LD_LIBRARY_PATH"] = os.pathsep.join(
                part
                for part in (
                    str(prefix / "lib"),
                    environment.get("LD_LIBRARY_PATH", ""),
                )
                if part
            )
            environment["CONDA_PREFIX"] = str(prefix)
        return environment

    def _git_config_path(self) -> Path:
        """Create an isolated Git config without changing the user's config."""

        identity = hashlib.sha256(str(self.root).encode("utf-8")).hexdigest()[:12]
        path = self.runtime_root / "state" / "git" / f"workspace-{identity}-isolated-v1.config"
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            return path
        lines = ("[safe]", f"\tdirectory = {self.root}", "")
        with path.open("x", encoding="utf-8", newline="\n") as handle:
            handle.write("\n".join(lines))
        return path

    def quarantine(
        self,
        source: Path,
        *,
        operation: str,
        reason: str,
    ) -> Path:
        """Move a failed staging path into quarantine; never delete it."""

        source_path = self.assert_write_path(source)
        if not source_path.exists():
            raise ConfigurationError(f"待隔离路径不存在: {source_path}")
        stamp = datetime.now(tz=UTC).strftime("%Y%m%dT%H%M%SZ")
        operation_id = f"{stamp}-{operation}-{uuid4().hex[:10]}"
        destination = self.runtime_root / "quarantine" / operation_id
        self.assert_write_path(destination)
        destination.mkdir(parents=True, exist_ok=False)
        moved = destination / source_path.name
        shutil.move(str(source_path), str(moved))
        metadata = destination / "quarantine.yaml"
        metadata.write_text(
            yaml.safe_dump(
                {
                    "schema_version": "0.1",
                    "operation_id": operation_id,
                    "reason": reason,
                    "source_path": str(source_path.relative_to(self.root)),
                    "quarantined_at": datetime.now(tz=UTC).isoformat(),
                },
                allow_unicode=True,
                sort_keys=False,
            ),
            encoding="utf-8",
        )
        return destination

    @classmethod
    def discover(cls, start: Path | None = None) -> WorkspaceContext:
        """Find the nearest tracked workspace marker without scanning user config."""

        active_context = _ACTIVE_CONTEXT.get()
        if (
            start is None
            and active_context is not None
            and (
                active_context.execution_scope is not None
                or not os.environ.get(EXECUTION_SCOPE_ENV)
            )
        ):
            return active_context
        candidates: list[Path] = []
        if start is not None:
            candidates.append(start.expanduser().resolve(strict=False))
        else:
            configured = os.environ.get(WORKSPACE_ENVIRONMENT_VARIABLE)
            if configured:
                candidates.append(Path(configured).expanduser().resolve(strict=False))
            candidates.append(Path.cwd().resolve())
            candidates.append(Path(__file__).resolve())
        visited: set[Path] = set()
        for candidate in candidates:
            current = candidate if candidate.is_dir() else candidate.parent
            for parent in (current, *current.parents):
                if parent in visited:
                    continue
                visited.add(parent)
                marker = parent / WORKSPACE_MARKER
                if marker.is_file():
                    context = cls.from_root(parent)
                    active = _ACTIVE_CONTEXT.get()
                    if active is not None:
                        if active.root != context.root:
                            raise PathPolicyError("Execution cannot cross workspace roots")
                        return active
                    configured_scope = os.environ.get(EXECUTION_SCOPE_ENV)
                    if configured_scope:
                        path = Path(configured_scope).expanduser()
                        scope = load_scope(
                            runtime_root=context.shared_runtime_root,
                            declaration_path=context.declaration_path,
                            path=path,
                        )
                        return replace(context, execution_scope=scope, execution_scope_path=path)
                    return context
        raise ConfigurationError(
            f"未找到 {WORKSPACE_MARKER}；请从 EasyDesign 仓库内运行 easydesign"
        )

    @classmethod
    def from_root(cls, root: Path) -> WorkspaceContext:
        resolved = root.expanduser().resolve(strict=True)
        marker = resolved / WORKSPACE_MARKER
        try:
            raw = yaml.safe_load(marker.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, yaml.YAMLError) as error:
            raise ConfigurationError(f"工作区声明无法读取: {marker}") from error
        try:
            declaration = WorkspaceDeclaration.model_validate(raw)
        except ValidationError as error:
            raise ConfigurationError(f"工作区声明校验失败: {error}") from error
        return cls(
            root=resolved,
            declaration_path=marker,
            declaration=declaration,
        )


def workspace_context(start: Path | None = None) -> WorkspaceContext:
    """Public shorthand used by legacy call sites during the migration."""

    return WorkspaceContext.discover(start)
