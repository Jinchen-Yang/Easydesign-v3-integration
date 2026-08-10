from __future__ import annotations

import json
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


def test_readme_supports_clean_machine_runtime_install_and_agent_native_cli() -> None:
    markdown = (ROOT / "README.md").read_text(encoding="utf-8")
    shell = _shell_blocks(markdown)
    assert "curl -LsSf https://astral.sh/uv/install.sh | sh" in shell
    assert "./scripts/bootstrap.py --index auto" in shell
    assert "./scripts/bootstrap.py --index aliyun" in shell
    assert "source .venv/bin/activate" in shell
    assert "Miniforge3-26.3.2-2-Linux-x86_64.sh" in shell
    assert "42260ffe3830fb953d5eee1bbb32229ff06aa7c3833c1ed7a9a0420a95685d94" in shell
    assert "easydesign runtime plan" in shell
    assert "easydesign runtime install" in shell
    assert "easydesign runtime jobs" in shell
    assert "easydesign runtime link" in shell
    assert "easydesign project init" in shell
    assert "easydesign project status" in shell
    assert "easydesign target prepare" in shell
    assert "easydesign view" in shell
    assert "easydesign step" not in shell
    assert "/root/autodl-tmp/Protein_design/easydesign-local" not in markdown
    assert "/root/autodl-tmp/Protein_design/easydesign-clean/runtime" not in markdown
    for forbidden in ("easydesign ui", "easydesign remote", "easydesign setup"):
        assert forbidden not in shell


def test_bootstrap_keeps_lock_resolution_separate_from_download_source() -> None:
    script = (ROOT / "scripts/bootstrap.py").read_text(encoding="utf-8")
    indexes = json.loads(
        (ROOT / "config/bootstrap-indexes.json").read_text(encoding="utf-8")
    )
    assert '"--frozen"' in script
    assert '"--require-hashes"' in script
    assert '"--default-index"' in script
    assert '"--proto-redir"' in script
    assert '"--insecure"' not in script
    assert {source["name"] for source in indexes["sources"]} == {
        "official",
        "aliyun",
        "tsinghua",
    }
    assert all(source["index_url"].startswith("https://") for source in indexes["sources"])


def test_scientific_backends_are_not_installed_into_uv_core() -> None:
    project_text = (ROOT / "pyproject.toml").read_text(encoding="utf-8").lower()
    for dependency in ("pymol", "boltzgen", "protenix", "scannet", "tnp"):
        assert f'"{dependency}' not in project_text
