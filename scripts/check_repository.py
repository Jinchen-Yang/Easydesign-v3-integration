"""使用标准库验证 EasyDesign 仓库基础结构。"""

from __future__ import annotations

import ast
import csv
import re
import sys
import tomllib
from datetime import datetime
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
    "DATA_SAFETY.md",
    "NANOBODY_FILTER_STANDARD_V1.md",
    "TODO.md",
    "TODO_NOW.md",
}
CORE_DEPENDENCIES = {
    "biopython",
    "gemmi",
    "httpx",
    "numpy",
    "platformdirs",
    "pydantic",
    "pyyaml",
}
CORE_MODULES = {
    "__init__.py",
    "artifacts.py",
    "attempts.py",
    "decisions.py",
    "evidence_links.py",
    "errors.py",
    "hashing.py",
    "identity.py",
    "manifests.py",
    "serialization.py",
    "tasks.py",
    "timestamps.py",
}
CORE_TESTS = {
    "conftest.py",
    "test_artifacts.py",
    "test_attempts.py",
    "test_decisions.py",
    "test_evidence_links.py",
    "test_hashing.py",
    "test_manifests.py",
    "test_serialization.py",
    "test_tasks.py",
}
ORCHESTRATION_MODULES = {
    "__init__.py",
    "config.py",
    "migration.py",
    "workspace.py",
}
ORCHESTRATION_TESTS = {
    "test_config.py",
    "test_migration.py",
    "test_workspace.py",
}
STAGE_HISTORY_SECTIONS = (
    "- 状态：",
    "- 完成时间：",
    "### 完成内容",
    "### 验证证据",
    "### 遇到的问题",
    "### 解决办法",
    "### 遗留问题",
)
HISTORY_TIMESTAMP_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[+-]\d{2}:\d{2}$")
IGNORED_REPOSITORY_DIRS = {
    "build",
    "dist",
    "models",
    "node_modules",
    "playwright-report",
    "runs",
    "runtime",
    "test-results",
}
FORBIDDEN_DELETE_CALLS = {
    "os.remove",
    "os.unlink",
    "os.rmdir",
    "shutil.rmtree",
}
FORBIDDEN_DELETE_METHODS = {"unlink", "rmdir"}


def destructive_write_calls() -> list[str]:
    """Find deletion primitives that bypass the quarantine-only write policy."""

    violations: list[str] = []
    source_root = ROOT / "src" / "easydesign"
    for path in sorted(source_root.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            function = node.func
            qualified: str | None = None
            if isinstance(function, ast.Attribute):
                if isinstance(function.value, ast.Name):
                    qualified = f"{function.value.id}.{function.attr}"
                elif function.attr in FORBIDDEN_DELETE_METHODS:
                    qualified = function.attr
            if (
                qualified in FORBIDDEN_DELETE_CALLS
                or qualified in FORBIDDEN_DELETE_METHODS
            ):
                violations.append(
                    f"{path.relative_to(ROOT)}:{node.lineno} 调用了 {qualified}"
                )
            if (
                isinstance(function, ast.Attribute)
                and function.attr in {"run", "Popen", "call", "check_call", "check_output"}
                and node.args
                and isinstance(node.args[0], (ast.List, ast.Tuple))
                and node.args[0].elts
            ):
                first = node.args[0].elts[0]
                if isinstance(first, ast.Constant) and first.value in {
                    "rm",
                    "unlink",
                    "rmdir",
                }:
                    violations.append(
                        f"{path.relative_to(ROOT)}:{node.lineno} 启动了删除命令"
                    )
    return violations


def require(condition: bool, message: str, errors: list[str]) -> None:
    if not condition:
        errors.append(message)


def require_completion_timestamp(
    record: str,
    record_label: str,
    errors: list[str],
) -> None:
    timestamps = [
        line.removeprefix("- 完成时间：").strip()
        for line in record.splitlines()
        if line.startswith("- 完成时间：")
    ]
    require(
        len(timestamps) == 1,
        f"{record_label} 必须且只能包含一个完成时间",
        errors,
    )
    if len(timestamps) == 1:
        valid_timestamp = HISTORY_TIMESTAMP_PATTERN.fullmatch(timestamps[0]) is not None
        if valid_timestamp:
            try:
                datetime.fromisoformat(timestamps[0])
            except ValueError:
                valid_timestamp = False
        require(
            valid_timestamp,
            (f"{record_label} 完成时间必须是带 UTC offset 的 RFC 3339 秒级时间: {timestamps[0]}"),
            errors,
        )


def project_markdown() -> list[Path]:
    return [
        path
        for path in ROOT.rglob("*.md")
        if not any(
            part.startswith(".") or part in IGNORED_REPOSITORY_DIRS
            for part in path.relative_to(ROOT).parts
        )
    ]


def main() -> int:
    errors: list[str] = []
    require(
        not destructive_write_calls(),
        "业务代码存在未经安全层封装的删除操作: "
        + "; ".join(destructive_write_calls()),
        errors,
    )

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

    actual_core_modules = {path.name for path in (ROOT / "src/easydesign/core").glob("*.py")}
    require(actual_core_modules == CORE_MODULES, "core 基础契约模块集合不一致", errors)
    actual_core_tests = {path.name for path in (ROOT / "tests/unit/core").glob("*.py")}
    require(CORE_TESTS <= actual_core_tests, "core 基础契约测试不完整", errors)
    actual_orchestration_modules = {
        path.name for path in (ROOT / "src/easydesign/orchestration").glob("*.py")
    }
    require(
        ORCHESTRATION_MODULES <= actual_orchestration_modules,
        "orchestration 配置、Workspace 或迁移模块不完整",
        errors,
    )
    actual_orchestration_tests = {
        path.name for path in (ROOT / "tests/unit/orchestration").glob("*.py")
    }
    require(
        ORCHESTRATION_TESTS <= actual_orchestration_tests,
        "orchestration 契约测试不完整",
        errors,
    )

    for stage in WORKFLOW_STAGES:
        base = ROOT / "workflow" / stage
        readme = base / "README.md"
        status = base / "STATUS.md"
        require(readme.is_file(), f"缺少 {readme.relative_to(ROOT)}", errors)
        if readme.is_file():
            require(readme.stat().st_size > 1_000, f"阶段文档内容不足: {stage}", errors)
        require(status.is_file(), f"缺少 {status.relative_to(ROOT)}", errors)
        if status.is_file():
            status_text = status.read_text(encoding="utf-8")
            for heading in (
                "## 顶层摘要",
                "## 当前结论",
                "## Now",
                "## Next",
                "## Blocked",
                "## 验证证据",
            ):
                require(heading in status_text, f"{stage}/STATUS 缺少区块: {heading}", errors)
        history_dir = base / "history"
        require(history_dir.is_dir(), f"缺少 {stage}/history", errors)
        if history_dir.is_dir():
            for history in sorted(history_dir.glob("*.md")):
                require(
                    re.fullmatch(r"\d{4}-\d{2}\.md", history.name) is not None,
                    f"Stage 历史文件名必须是 YYYY-MM.md: {history.relative_to(ROOT)}",
                    errors,
                )
                history_text = history.read_text(encoding="utf-8")
                records = re.split(r"(?m)^## ", history_text)[1:]
                require(
                    bool(records),
                    f"Stage 历史没有工作项记录: {history.relative_to(ROOT)}",
                    errors,
                )
                for record_number, record in enumerate(records, start=1):
                    for section in STAGE_HISTORY_SECTIONS:
                        require(
                            section in record,
                            (
                                f"{history.relative_to(ROOT)} 第 {record_number} 条记录"
                                f"缺少: {section}"
                            ),
                            errors,
                        )
                    require_completion_timestamp(
                        record,
                        (f"{history.relative_to(ROOT)} 第 {record_number} 条记录"),
                        errors,
                    )
                if status.is_file():
                    require(
                        f"history/{history.name}" in status_text,
                        f"{stage}/STATUS 历史索引未链接 {history.name}",
                        errors,
                    )
        require((base / "examples/.gitkeep").is_file(), f"缺少 {stage}/examples 占位", errors)
        require(not (base / "CONTRACT.md").exists(), f"{stage} 不应再有独立 CONTRACT", errors)

    expected_docs = {
        "docs/ARCHITECTURE.md",
        "docs/legacy/BASELINE.md",
        "configs/README.md",
        "examples/README.md",
        "resources/README.md",
        "runtime/README.md",
        "workflow/README.md",
    }
    for relative in expected_docs:
        require((ROOT / relative).is_file(), f"缺少 {relative}", errors)

    # Allow the seven Stage directories to keep one monthly history file each
    # while still preventing ungoverned one-off documents from accumulating.
    # Packaged PML Skill bodies are executable prompt assets with one required
    # SKILL.md per Skill, not standalone project documentation.
    governed_markdown = [
        path
        for path in markdown
        if "src/easydesign/ui/pml_skill_library"
        not in path.relative_to(ROOT).as_posix()
    ]
    require(
        len(governed_markdown) <= 53,
        f"Markdown 数量超过精简上限: {len(governed_markdown)}",
        errors,
    )

    with (ROOT / "pyproject.toml").open("rb") as handle:
        project = tomllib.load(handle)["project"]
    require(project["version"] == "0.1.0.dev41", "项目版本异常", errors)
    require(project["requires-python"] == ">=3.11,<3.13", "Python 基线异常", errors)
    require(
        project.get("scripts") == {"easydesign": "easydesign.cli:main"},
        "Developer Preview 必须只提供统一 easydesign 命令",
        errors,
    )
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
        require(
            "-e .[dev,ui]" in environment_text,
            "Conda 环境未 editable 安装开发与 UI 依赖",
            errors,
        )

    protenix_environment = ROOT / "environments/protenix-v2.yml"
    require(protenix_environment.is_file(), "缺少 Protenix-v2 独立环境声明", errors)
    if protenix_environment.is_file():
        protenix_environment_text = protenix_environment.read_text(encoding="utf-8")
        for requirement in (
            "name: protenix-v2",
            "python=3.11.15",
            "cuda-nvcc=12.6.85",
            "protenix==2.0.0",
        ):
            require(
                requirement in protenix_environment_text,
                f"Protenix-v2 环境缺少固定项: {requirement}",
                errors,
            )

    pymol_environment = ROOT / "environments/pymol-pse.yml"
    require(pymol_environment.is_file(), "缺少 PyMOL PSE 独立环境声明", errors)
    if pymol_environment.is_file():
        pymol_environment_text = pymol_environment.read_text(encoding="utf-8")
        for requirement in (
            "name: pymol-pse",
            "conda-forge",
            "python=3.11",
            "pymol-open-source=3.1.0",
        ):
            require(
                requirement in pymol_environment_text,
                f"PyMOL PSE 环境缺少固定项: {requirement}",
                errors,
            )

    scannet_environment = ROOT / "environments/scannet-epitope.yml"
    require(scannet_environment.is_file(), "缺少 ScanNet 独立环境声明", errors)
    if scannet_environment.is_file():
        scannet_environment_text = scannet_environment.read_text(encoding="utf-8")
        for requirement in (
            "name: scannet-epitope",
            "python=3.6.12",
            "tensorflow-gpu==1.14.0",
        ):
            require(
                requirement in scannet_environment_text,
                f"ScanNet 环境缺少固定项: {requirement}",
                errors,
            )

    agent_text = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    for heading in ("开始任务前", "实施规则", "完成任务前", "阻塞与询问"):
        require(heading in agent_text, f"AGENTS 缺少工作协议: {heading}", errors)

    todo_now = (ROOT / "TODO_NOW.md").read_text(encoding="utf-8")
    for heading in (
        "## 七阶段实时摘要",
        "## Now",
        "## Next",
        "## Blocked",
        "## 历史索引",
    ):
        require(heading in todo_now, f"TODO_NOW 缺少区块: {heading}", errors)

    shared_history_root = ROOT / "docs/history"
    for history in sorted(shared_history_root.glob("????-??/TODO_NOW.md")):
        records = re.split(
            r"(?m)^## ",
            history.read_text(encoding="utf-8"),
        )[1:]
        require(
            bool(records),
            f"顶层 TODO_NOW 历史没有完成记录: {history.relative_to(ROOT)}",
            errors,
        )
        for record_number, record in enumerate(records, start=1):
            require_completion_timestamp(
                record,
                (f"{history.relative_to(ROOT)} 第 {record_number} 条记录"),
                errors,
            )

    architecture = (ROOT / "docs/ARCHITECTURE.md").read_text(encoding="utf-8")
    for concept in (
        "ArtifactRef",
        "Attempt",
        "StageManifest",
        "RunManifest",
        "允许的依赖方向",
        "input-snapshot",
        "_development",
        "attempt-0001",
    ):
        require(concept in architecture, f"架构文档缺少概念: {concept}", errors)

    apoe_input = ROOT / "examples/stage01-apoe/input"
    for filename in (
        "apoe4-fragment-41-183.fasta",
        "easydesign.yaml",
        "source.json",
    ):
        require((apoe_input / filename).is_file(), f"APOE 用户输入示例缺少: {filename}", errors)
    require(
        not (apoe_input / "protenix-input.json").exists(),
        "Protenix JSON 是 adapter 产物，不能作为 APOE 用户输入提交",
        errors,
    )

    ignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
    for pattern in ("runs/*", "projects/*", "models/*", "*.safetensors", ".env"):
        require(pattern in ignore, f"缺少 ignore 规则: {pattern}", errors)

    require(not (ROOT / "LICENSE").exists(), "IP 决策前不得添加 LICENSE", errors)
    register = ROOT / "resources/provenance/ASSET_REGISTER.tsv"
    expected_asset_header = [
        "asset_id",
        "path",
        "source_url",
        "source_revision_or_checksum",
        "license",
        "review_status",
        "notes",
    ]
    with register.open(encoding="utf-8", newline="") as handle:
        asset_rows = list(csv.reader(handle, delimiter="\t"))
    require(
        bool(asset_rows) and asset_rows[0] == expected_asset_header,
        "资产登记表头异常",
        errors,
    )
    for row_number, row in enumerate(asset_rows[1:], start=2):
        require(
            len(row) == len(expected_asset_header),
            f"资产登记第 {row_number} 行列数异常",
            errors,
        )
        if len(row) != len(expected_asset_header):
            continue
        require(all(row), f"资产登记第 {row_number} 行存在空字段", errors)
        require(
            row[5]
            in {
                "approved-redistribution",
                "approved-runtime-only",
                "approved-vendored",
                "approved-private-repository",
                "awaiting-user-approval",
            },
            f"资产登记第 {row_number} 行审查状态无法识别",
            errors,
        )

    registered_asset_ids = {
        row[0] for row in asset_rows[1:] if len(row) == len(expected_asset_header)
    }
    runtime_catalog_text = (ROOT / "configs/runtime-assets.yaml").read_text(
        encoding="utf-8"
    )
    runtime_asset_ids = set(
        re.findall(r"(?m)^  - asset_id: ([a-z0-9][a-z0-9-]+)$", runtime_catalog_text)
    )
    require(
        len(runtime_asset_ids) == 15,
        f"runtime 资产目录数量异常: {len(runtime_asset_ids)}",
        errors,
    )
    require(
        runtime_asset_ids <= registered_asset_ids,
        (
            "runtime 资产未同步到长期来源登记: "
            f"{sorted(runtime_asset_ids - registered_asset_ids)}"
        ),
        errors,
    )

    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print("仓库精简结构检查通过。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
