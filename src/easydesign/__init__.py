"""EasyDesign contract-first workflow package."""

import tomllib
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path


def _resolve_version() -> str:
    """Prefer the checked-out source version over stale installed metadata."""

    pyproject = Path(__file__).resolve().parents[2] / "pyproject.toml"
    if pyproject.is_file():
        project = tomllib.loads(pyproject.read_text(encoding="utf-8")).get("project", {})
        source_version = project.get("version")
        if isinstance(source_version, str) and source_version:
            return source_version
    try:
        return version("easydesign")
    except PackageNotFoundError:
        return "0+unknown"


__version__ = _resolve_version()

from .workspace_context import WorkspaceContext, WorkspaceDeclaration  # noqa: E402

__all__ = ["WorkspaceContext", "WorkspaceDeclaration", "__version__"]
