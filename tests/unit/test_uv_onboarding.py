from __future__ import annotations

import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _shell_blocks(markdown: str) -> str:
    return "\n".join(re.findall(r"```bash\n(.*?)```", markdown, flags=re.DOTALL))


def test_uv_files_and_local_distribution_identity_are_committed() -> None:
    assert (ROOT / ".python-version").read_text(encoding="utf-8") == "3.11\n"
    assert (ROOT / "uv.lock").is_file()
    with (ROOT / "pyproject.toml").open("rb") as handle:
        project = tomllib.load(handle)["project"]
    assert project["name"] == "easydesign-local"
    assert project["version"] == "0.1.0.dev1"
    assert project["scripts"] == {"easydesign": "easydesign.cli:main"}
    assert project["requires-python"] == ">=3.11,<3.13"
    assert project["classifiers"][-1] == "Private :: Do Not Upload"


def test_readme_matches_local_runtime_link_and_agent_native_cli() -> None:
    markdown = (ROOT / "README.md").read_text(encoding="utf-8")
    shell = _shell_blocks(markdown)
    assert "uv sync --frozen --extra dev" in shell
    assert "source .venv/bin/activate" in shell
    assert "easydesign runtime link" in shell
    assert "easydesign project init" in shell
    assert "easydesign project status" in shell
    assert "easydesign target prepare" in shell
    assert "easydesign view" in shell
    assert "easydesign step" not in shell
    for forbidden in ("easydesign ui", "easydesign remote", "easydesign setup"):
        assert forbidden not in shell


def test_scientific_backends_are_not_installed_into_uv_core() -> None:
    project_text = (ROOT / "pyproject.toml").read_text(encoding="utf-8").lower()
    for dependency in ("pymol", "boltzgen", "protenix", "scannet", "tnp"):
        assert f'"{dependency}' not in project_text
