from __future__ import annotations

import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
COMPONENTS = (
    "pymol-pse",
    "boltzgen",
    "protenix-v2",
    "scannet-epitope",
    "tnp",
)


def _shell_blocks(markdown: str) -> str:
    return "\n".join(re.findall(r"```bash\n(.*?)```", markdown, flags=re.DOTALL))


def test_uv_files_and_python_contract_are_committed() -> None:
    assert (ROOT / ".python-version").read_text(encoding="utf-8") == "3.11\n"
    assert (ROOT / "uv.lock").is_file()
    with (ROOT / "pyproject.toml").open("rb") as handle:
        project = tomllib.load(handle)["project"]
    assert re.fullmatch(r"\d+\.\d+\.\d+(?:\.dev\d+)?", project["version"])
    assert project["requires-python"] == ">=3.11,<3.13"
    assert project["classifiers"][-1] == "Private :: Do Not Upload"


def test_readmes_match_the_real_setup_and_remote_cli_contract() -> None:
    for filename in ("README.md", "README.en.md"):
        markdown = (ROOT / filename).read_text(encoding="utf-8")
        shell = _shell_blocks(markdown)
        assert "uv sync --frozen --extra ui" in shell
        assert "source .venv/bin/activate" in shell
        assert "uv run easydesign" not in shell
        assert project_version_not_copied(markdown)
        assert "/absolute/path/to/conda" not in markdown
        for component in COMPONENTS:
            assert f"easydesign setup --component {component} --plan" in shell
            assert f"easydesign setup --component {component} --detach" in shell
        assert "--accept-license ASSET_ID_1" in shell
        assert "easydesign setup --status --job-id JOB_ID" in shell
        assert "easydesign remote pair-scan" in shell
        assert "easydesign remote pair-begin suzhou2" in shell
        assert "ssh-copy-id" in shell
        assert "easydesign remote pair-confirm suzhou2" in shell
        assert "easydesign remote unpair suzhou2 --confirmed" in shell
        assert "easydesign ui serve" in shell


def project_version_not_copied(markdown: str) -> bool:
    with (ROOT / "pyproject.toml").open("rb") as handle:
        version = tomllib.load(handle)["project"]["version"]
    return version not in markdown


def test_readmes_do_not_mix_scientific_backends_into_uv_core() -> None:
    project_text = (ROOT / "pyproject.toml").read_text(encoding="utf-8").lower()
    for dependency in ("pymol", "boltzgen", "protenix", "scannet", "tnp"):
        assert f'"{dependency}' not in project_text
