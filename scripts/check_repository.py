"""Validate the EasyDesign repository foundation using only the standard library."""

from __future__ import annotations

import sys
import tomllib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_STAGES = (
    "01-target-preparation",
    "02-hotspot-discovery",
    "03-boltzgen-configuration",
    "04-pilot-generation",
    "05-pilot-filtering",
    "06-scale-generation-and-refolding",
    "07-final-filtering-and-selection",
)
PYTHON_STAGES = (
    "s01_target_preparation",
    "s02_hotspot_discovery",
    "s03_boltzgen_configuration",
    "s04_pilot_generation",
    "s05_pilot_filtering",
    "s06_scale_generation_and_refolding",
    "s07_final_filtering_and_selection",
)
ROOT_PAIRS = (
    "README",
    "PROJECT_CHARTER",
    "CONTRIBUTING",
    "AGENTS",
    "TODO",
    "TODO_NOW",
    "CHANGELOG",
)


def require(condition: bool, message: str, errors: list[str]) -> None:
    if not condition:
        errors.append(message)


def main() -> int:
    errors: list[str] = []

    for stem in ROOT_PAIRS:
        require((ROOT / f"{stem}.md").is_file(), f"missing {stem}.md", errors)
        require(
            (ROOT / f"{stem}.zh-CN.md").is_file(),
            f"missing {stem}.zh-CN.md",
            errors,
        )

    actual_workflow = tuple(
        path.name
        for path in sorted((ROOT / "workflow").iterdir())
        if path.is_dir() and path.name[:1].isdigit()
    )
    require(actual_workflow == WORKFLOW_STAGES, "workflow stage set/order differs", errors)

    actual_python = tuple(
        path.name
        for path in sorted((ROOT / "src/easydesign/stages").iterdir())
        if path.is_dir() and path.name.startswith("s")
    )
    require(actual_python == PYTHON_STAGES, "Python stage set/order differs", errors)

    for stage in WORKFLOW_STAGES:
        base = ROOT / "workflow" / stage
        for relative in (
            "README.md",
            "README.zh-CN.md",
            "CONTRACT.md",
            "CONTRACT.zh-CN.md",
            "examples/README.md",
            "examples/README.zh-CN.md",
        ):
            path = base / relative
            require(path.is_file(), f"missing {path.relative_to(ROOT)}", errors)
            if path.is_file():
                require(path.stat().st_size > 100, f"empty-looking {path.relative_to(ROOT)}", errors)

    with (ROOT / "pyproject.toml").open("rb") as handle:
        project = tomllib.load(handle)["project"]
    require(project["version"] == "0.1.0.dev0", "unexpected project version", errors)
    require(project["requires-python"] == ">=3.11,<3.13", "unexpected Python baseline", errors)
    require("scripts" not in project, "public CLI must not exist in foundation", errors)

    ignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
    for pattern in ("runs/*", "models/*", "*.safetensors", ".env"):
        require(pattern in ignore, f"missing ignore rule: {pattern}", errors)

    require(not (ROOT / "LICENSE").exists(), "LICENSE must be absent pending IP decision", errors)
    require(
        (ROOT / "resources/provenance/ASSET_REGISTER.tsv").read_text(encoding="utf-8").count("\n") == 1,
        "foundation must not include unreviewed asset rows",
        errors,
    )

    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print("Repository foundation checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
