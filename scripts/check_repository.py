"""使用标准库验证 EasyDesign 仓库基础结构。"""

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
ROOT_DOCS = {
    "README.md",
    "PROJECT_CHARTER.md",
    "AGENTS.md",
    "TODO.md",
    "TODO_NOW.md",
}
CORE_DEPENDENCIES = {
    "biopython",
    "gemmi",
    "httpx",
    "numpy",
    "pydantic",
    "pyyaml",
}


def require(condition: bool, message: str, errors: list[str]) -> None:
    if not condition:
        errors.append(message)


def project_markdown() -> list[Path]:
    return [
        path
        for path in ROOT.rglob("*.md")
        if not any(part.startswith(".") for part in path.relative_to(ROOT).parts)
    ]


def main() -> int:
    errors: list[str] = []

    actual_root_docs = {path.name for path in ROOT.glob("*.md")}
    require(actual_root_docs == ROOT_DOCS, "根目录 Markdown 集合不符合精简规则", errors)
    markdown = project_markdown()
    require(
        not [path for path in markdown if path.name.endswith(".zh-CN.md")],
        "开发期不得保留独立英文/中文配对文档",
        errors,
    )

    actual_workflow = tuple(
        path.name
        for path in sorted((ROOT / "workflow").iterdir())
        if path.is_dir() and path.name[:1].isdigit()
    )
    require(actual_workflow == WORKFLOW_STAGES, "workflow 阶段集合或顺序不一致", errors)

    actual_python = tuple(
        path.name
        for path in sorted((ROOT / "src/easydesign/stages").iterdir())
        if path.is_dir() and path.name.startswith("s")
    )
    require(actual_python == PYTHON_STAGES, "Python stage 集合或顺序不一致", errors)

    for stage in WORKFLOW_STAGES:
        base = ROOT / "workflow" / stage
        readme = base / "README.md"
        require(readme.is_file(), f"缺少 {readme.relative_to(ROOT)}", errors)
        if readme.is_file():
            require(readme.stat().st_size > 1_000, f"阶段文档内容不足: {stage}", errors)
        require((base / "examples/.gitkeep").is_file(), f"缺少 {stage}/examples 占位", errors)
        require(not (base / "CONTRACT.md").exists(), f"{stage} 不应再有独立 CONTRACT", errors)

    expected_docs = {
        "docs/ARCHITECTURE.md",
        "docs/legacy/BASELINE.md",
        "configs/README.md",
        "examples/README.md",
        "resources/README.md",
        "workflow/README.md",
    }
    for relative in expected_docs:
        require((ROOT / relative).is_file(), f"缺少 {relative}", errors)

    markdown_count = len(markdown)
    require(markdown_count == 18, f"Markdown 数量应为 18，实际为 {markdown_count}", errors)

    with (ROOT / "pyproject.toml").open("rb") as handle:
        project = tomllib.load(handle)["project"]
    require(project["version"] == "0.1.0.dev0", "项目版本异常", errors)
    require(project["requires-python"] == ">=3.11,<3.13", "Python 基线异常", errors)
    require("scripts" not in project, "基础阶段不得提供公开 CLI", errors)
    dependency_names = {
        dependency.split(";", 1)[0]
        .split("[", 1)[0]
        .split("<", 1)[0]
        .split(">", 1)[0]
        .split("=", 1)[0]
        .strip()
        .lower()
        for dependency in project["dependencies"]
    }
    require(
        CORE_DEPENDENCIES <= dependency_names,
        f"核心依赖不完整: {sorted(CORE_DEPENDENCIES - dependency_names)}",
        errors,
    )

    environment = ROOT / "environment.yml"
    require(environment.is_file(), "缺少 environment.yml", errors)
    if environment.is_file():
        environment_text = environment.read_text(encoding="utf-8")
        require("name: easydesign-core" in environment_text, "Conda 环境名异常", errors)
        require("python=3.11" in environment_text, "Conda 环境必须使用 Python 3.11", errors)
        require("-e .[dev]" in environment_text, "Conda 环境未 editable 安装开发依赖", errors)

    agent_text = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    for heading in ("开始任务前", "实施规则", "完成任务前", "阻塞与询问"):
        require(heading in agent_text, f"AGENTS 缺少工作协议: {heading}", errors)

    todo_now = (ROOT / "TODO_NOW.md").read_text(encoding="utf-8")
    for heading in ("## Now", "## Next", "## Blocked", "## 只追加工作日志"):
        require(heading in todo_now, f"TODO_NOW 缺少区块: {heading}", errors)

    architecture = (ROOT / "docs/ARCHITECTURE.md").read_text(encoding="utf-8")
    for concept in ("ArtifactRef", "Attempt", "StageManifest", "RunManifest", "允许的依赖方向"):
        require(concept in architecture, f"架构文档缺少概念: {concept}", errors)

    ignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
    for pattern in ("runs/*", "models/*", "*.safetensors", ".env"):
        require(pattern in ignore, f"缺少 ignore 规则: {pattern}", errors)

    require(not (ROOT / "LICENSE").exists(), "IP 决策前不得添加 LICENSE", errors)
    register = ROOT / "resources/provenance/ASSET_REGISTER.tsv"
    require(register.read_text(encoding="utf-8").count("\n") == 1, "存在未审查资产记录", errors)

    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print("仓库精简结构检查通过。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
