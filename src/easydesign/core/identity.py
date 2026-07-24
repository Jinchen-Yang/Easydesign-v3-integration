"""Git checkout、dirty 工作树和已安装 package 的确定性代码身份。"""

from __future__ import annotations

import hashlib
import subprocess
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from .errors import ConfigurationError
from .hashing import sha256_file
from .manifests import CodeIdentity, CodeIdentitySource

_IGNORED_PARTS = {"__pycache__", ".git", ".mypy_cache", ".pytest_cache", ".ruff_cache"}
_IGNORED_SUFFIXES = {".pyc", ".pyo"}


def _distribution_version() -> str:
    try:
        return version("easydesign")
    except PackageNotFoundError:
        return "0+unknown"


def _identity_files(root: Path) -> tuple[Path, ...]:
    files = []
    for path in root.rglob("*"):
        relative = path.relative_to(root)
        if (
            path.is_file()
            and not path.is_symlink()
            and not _IGNORED_PARTS.intersection(relative.parts)
            and path.suffix not in _IGNORED_SUFFIXES
        ):
            files.append(path)
    return tuple(sorted(files, key=lambda item: item.relative_to(root).as_posix()))


def package_tree_sha256(package_root: Path, *, metadata_files: tuple[Path, ...] = ()) -> str:
    """对 package 文件与显式元数据生成路径敏感的稳定 SHA-256。"""

    root = package_root.resolve(strict=True)
    digest = hashlib.sha256()
    for path in _identity_files(root):
        relative = path.relative_to(root).as_posix()
        digest.update(f"package/{relative}\0{path.stat().st_size}\0".encode())
        digest.update(sha256_file(path).encode())
        digest.update(b"\n")
    for path in sorted(metadata_files, key=lambda item: item.name):
        resolved = path.resolve(strict=True)
        digest.update(f"metadata/{resolved.name}\0{resolved.stat().st_size}\0".encode())
        digest.update(sha256_file(resolved).encode())
        digest.update(b"\n")
    return digest.hexdigest()


def _git_output(repository_root: Path, *arguments: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(repository_root), *arguments],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if completed.returncode != 0:
        raise ConfigurationError(
            f"Git 代码身份探针失败: {' '.join(arguments)}: {completed.stderr.strip()}"
        )
    return completed.stdout.strip()


def resolve_code_identity(
    *,
    package_root: Path,
    repository_root: Path | None = None,
    distribution_version: str | None = None,
) -> CodeIdentity:
    """解析实际运行代码身份；dirty checkout 使用内容哈希而不是伪造 clean commit。"""

    package = package_root.resolve(strict=True)
    selected_version = distribution_version or _distribution_version()
    if repository_root is not None and (repository_root / ".git").exists():
        repository = repository_root.resolve(strict=True)
        commit = _git_output(repository, "rev-parse", "HEAD")
        if len(commit) != 40:
            raise ConfigurationError(f"Git commit 不是完整 40 位 SHA: {commit}")
        dirty = bool(_git_output(repository, "status", "--porcelain", "--untracked-files=all"))
        if not dirty:
            return CodeIdentity(
                version=selected_version,
                source=CodeIdentitySource.GIT,
                git_commit=commit,
                dirty=False,
            )
        metadata = tuple(
            path for path in (repository / "pyproject.toml",) if path.is_file()
        )
        return CodeIdentity(
            version=selected_version,
            source=CodeIdentitySource.WORKING_TREE,
            git_commit=commit,
            dirty=True,
            content_sha256=package_tree_sha256(package, metadata_files=metadata),
        )
    return CodeIdentity(
        version=selected_version,
        source=CodeIdentitySource.INSTALLED_PACKAGE,
        dirty=False,
        content_sha256=package_tree_sha256(package),
    )
