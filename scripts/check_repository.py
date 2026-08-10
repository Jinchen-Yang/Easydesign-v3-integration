"""Fast structural guard for the permanent local-only product branch."""

from __future__ import annotations

import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STAGES = (
    "01-target-preparation",
    "02-hotspot-discovery",
    "03-boltzgen-configuration",
    "04-pilot-generation",
    "05-pilot-filtering",
    "06-scale-generation-and-refolding",
    "07-final-filtering-and-selection",
)
FORBIDDEN_PATHS = (
    "src/easydesign/ui",
    "web/workbench",
    "src/easydesign/managed_protocol.py",
    "src/easydesign/backends/executors/ssh_remote.py",
    "src/easydesign/orchestration/remote_execution.py",
    "src/easydesign/orchestration/ssh_pairing.py",
    "src/easydesign/orchestration/evidence_adoption.py",
    "src/easydesign/core/evidence_links.py",
    "scripts/local_ui_release.py",
    "scripts/publish_ui_build.py",
    "scripts/serve_ui_evidence_bundle.py",
    "tests/fixtures/managed_protocol",
    "docs/UI_WORKBENCH.md",
    "docs/CASE_REGISTRY.md",
    "docs/agent/UI_AND_REPORTING.md",
    "docs/agent/RELEASE_AND_REMOTE.md",
)
REQUIRED_LOCAL_FILES = (
    "setup.cfg",
    "config/bootstrap-indexes.json",
    "scripts/bootstrap.py",
    "src/easydesign/cli.py",
    "src/easydesign/local_worker.py",
    "src/easydesign/runtime_guard.py",
    "src/easydesign/orchestration/local_jobs.py",
    "src/easydesign/orchestration/local_project.py",
    "src/easydesign/orchestration/research.py",
    "src/easydesign/orchestration/research_models.py",
    "src/easydesign/orchestration/runtime_link.py",
    "src/easydesign/orchestration/runtime_setup.py",
    "src/easydesign/orchestration/setup_jobs.py",
    "src/easydesign/setup_worker.py",
    "src/easydesign/reporting/evidence_viewer.py",
    "src/easydesign/reporting/stage02_overlay.py",
    "web/target-viewer/package.json",
    "examples/apoe-ui-demo/README.md",
    ".agents/skills/easydesign-research/SKILL.md",
    ".agents/skills/easydesign-research/references/target-and-site.md",
    ".agents/skills/easydesign-research/references/strategy-yaml.md",
    ".agents/skills/easydesign-research/references/pilot-diagnosis.md",
    ".agents/skills/easydesign-research/references/scale-and-selection.md",
)
ACTIVE_LOCAL_POLICY_FILES = (
    "AGENTS.md",
    "DATA_SAFETY.md",
    "DEVELOPMENT.md",
    "README.md",
    ".agents/skills/easydesign-research/SKILL.md",
    "docs/ARCHITECTURE.md",
    "docs/CHARTER.md",
    "docs/PRODUCT_PHILOSOPHY.md",
    "docs/README.en.md",
    "docs/ROADMAP.md",
    "docs/agent/LOCAL_CLI_AND_VIEWER.md",
    "docs/agent/RUNTIME_AND_DATA.md",
    "docs/decisions/ADR-0004-multi-strategy-promotion-and-shared-scale-budget.md",
    "docs/workflow/README.md",
    "environments/README.md",
    *(f"docs/workflow/{stage}.md" for stage in STAGES),
)
STALE_REMOTE_POLICY_TOKENS = (
    "managed-ssh",
    "RemoteJobBundle",
)


def main() -> int:
    errors: list[str] = []
    agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    if len(agents.splitlines()) > 90 or len(agents.encode("utf-8")) > 12_000:
        errors.append("AGENTS.md 超过 90 行或 12KB 预算")
    guides = {
        path.relative_to(ROOT).as_posix()
        for path in (ROOT / "docs/agent").glob("*.md")
    }
    expected_guides = {
        "docs/agent/SCIENTIFIC_PIPELINE.md",
        "docs/agent/LOCAL_CLI_AND_VIEWER.md",
        "docs/agent/RUNTIME_AND_DATA.md",
    }
    if guides != expected_guides:
        errors.append(f"Agent 专题指南集合不精确: {sorted(guides)}")
    for relative in FORBIDDEN_PATHS:
        if (ROOT / relative).exists():
            errors.append(f"local 分支禁止路径重新出现: {relative}")
    historical_documents = tuple(
        ROOT / "docs" / name
        for name in (
            "BASELINE.md",
            "ROADMAP_HISTORY_2026-07.md",
            "ROADMAP_HISTORY_2026-08.md",
        )
    ) + tuple(
        (ROOT / "docs" / "workflow").glob("*-2026-??.md")
    )
    for path in historical_documents:
        if path.exists():
            errors.append(f"旧产品工作日志不得重新成为当前仓库入口: {path.relative_to(ROOT)}")
    for relative in ("build", "src/easydesign.egg-info", "src/easydesign_local.egg-info"):
        if (ROOT / relative).exists():
            errors.append(f"构建产物必须位于 runtime，禁止源码树路径: {relative}")
    for relative in REQUIRED_LOCAL_FILES:
        if not (ROOT / relative).is_file():
            errors.append(f"local 产品缺少文件: {relative}")
    for relative in ACTIVE_LOCAL_POLICY_FILES:
        text = (ROOT / relative).read_text(encoding="utf-8")
        for token in STALE_REMOTE_POLICY_TOKENS:
            if token in text:
                errors.append(f"当前本地规范残留旧远程或固定路径: {relative}: {token}")
    if "easydesign-workspace.yaml" not in agents:
        errors.append("AGENTS.md 必须通过 workspace marker 描述可移植 clone 根")
    for stage in STAGES:
        for suffix in (".md", "-status.md"):
            path = ROOT / "docs/workflow" / f"{stage}{suffix}"
            if not path.is_file():
                errors.append(f"缺少科学 Stage 文档: {path.relative_to(ROOT)}")
    with (ROOT / "pyproject.toml").open("rb") as handle:
        document = tomllib.load(handle)
    project = document["project"]
    if project.get("name") != "easydesign-local":
        errors.append("distribution 必须是 easydesign-local")
    if project.get("version") != "0.1.0.dev1":
        errors.append("local 产品初始版本必须是 0.1.0.dev1")
    if project.get("scripts") != {"easydesign": "easydesign.cli:main"}:
        errors.append("终端入口必须且只能是 easydesign")
    if "ui" in project.get("optional-dependencies", {}):
        errors.append("local 产品禁止 FastAPI/Uvicorn UI extra")
    package_data = document.get("tool", {}).get("setuptools", {}).get("package-data", {})
    if any("ui/" in value for values in package_data.values() for value in values):
        errors.append("local wheel 禁止 UI package data")
    cli_text = (ROOT / "src/easydesign/cli.py").read_text(encoding="utf-8").lower()
    if 'add_parser("step"' in cli_text:
        errors.append("Agent-native local CLI 禁止重新暴露 step parser")
    if (ROOT / "src/easydesign/orchestration/local_steps.py").exists():
        errors.append("Agent-native local 产品禁止保留旧 step 产品壳")
    for token in ("managed-ssh", "ssh_pairing"):
        if token in cli_text:
            errors.append(f"local CLI 禁止远程控制词: {token}")
    python_text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted((ROOT / "src/easydesign").rglob("*.py"))
    )
    for token in ("EASYDESIGN_REMOTE_EXECUTOR_ID", "ssh-remote-"):
        if token in python_text:
            errors.append(f"local Python 产品残留远程执行 token: {token}")
    marker = (ROOT / "easydesign-workspace.yaml").read_text(encoding="utf-8")
    for value in (
        "runtime_root: runtime",
        "projects_root: workspace/projects",
        "runs_root: workspace/runs",
    ):
        if value not in marker:
            errors.append(f"workspace marker 缺少: {value}")
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    print("repository structure: local-only OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
