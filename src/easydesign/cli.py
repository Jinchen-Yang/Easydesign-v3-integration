"""EasyDesign Developer Preview 的薄命令行入口。"""

from __future__ import annotations

import argparse
import json
import sys
import time
import traceback
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from pydantic import BaseModel

import easydesign
from easydesign.backends.executors import ManagedWorkerProbe
from easydesign.core import (
    ArtifactIntegrityError,
    ArtifactNotFoundError,
    ConfigurationError,
    EasyDesignError,
    RunManifest,
    SerializationError,
    load_model,
)
from easydesign.orchestration.application import (
    DiagnosticReport,
    PipelineExecution,
    RunPlan,
    continue_pipeline_after_decision,
    diagnose_runtime,
    execute_pipeline,
    list_runs,
    migrate_run_configuration,
    resume_pipeline,
    show_run,
    validate_run_configuration,
)
from easydesign.orchestration.decisions import (
    approve_decision,
    export_decision,
    show_decision,
)
from easydesign.orchestration.evidence_adoption import adopt_remote_scale_evidence
from easydesign.orchestration.hotspots import approve_hotspots, export_hotspot_review
from easydesign.orchestration.profile import (
    default_runtime_profile_path,
    initialize_runtime_profile,
    load_runtime_profile,
)
from easydesign.orchestration.project import initialize_project
from easydesign.orchestration.project_catalog import (
    archive_project,
    list_project_catalog,
    prune_archived_project_shells,
    restore_project,
    select_project_primary_run,
)
from easydesign.orchestration.remote_execution import (
    list_managed_remote_submissions,
    list_remote_executor_ids,
    list_remote_job_records,
    observe_managed_pipeline,
    observe_remote_pipeline,
    probe_managed_executor,
    probe_remote_executor,
    read_remote_job_record,
    read_remote_status,
    read_remote_submission,
    require_managed_probe_compatible,
    resume_remote_pipeline,
    submit_managed_pipeline,
    submit_remote_pipeline,
    sync_remote_pipeline,
)
from easydesign.orchestration.runtime_setup import (
    SETUP_COMPONENT_IDS,
    asset_status,
    environment_status,
    import_legacy_deployment,
    setup_plan,
    setup_workspace,
)
from easydesign.orchestration.setup_jobs import (
    launch_setup_job,
    list_setup_jobs,
    read_setup_job,
)
from easydesign.orchestration.ssh_pairing import (
    RemoteExecutorRegistry,
    public_key_install_command,
    scan_host_identity,
)
from easydesign.orchestration.stage04 import Stage04Execution
from easydesign.orchestration.stage05 import Stage05Execution
from easydesign.orchestration.stage06 import Stage06Execution
from easydesign.orchestration.stage07 import Stage07Execution
from easydesign.reporting import (
    HOST,
    create_target_viewer_server,
    resolve_target_viewer_argument,
)
from easydesign.stages.s02_hotspot_discovery import RegionMethod
from easydesign.workspace_context import WorkspaceContext


def _json_text(value: BaseModel | tuple[BaseModel, ...] | dict[str, Any]) -> str:
    if isinstance(value, BaseModel):
        payload: object = value.model_dump(mode="json")
    elif isinstance(value, tuple):
        payload = [item.model_dump(mode="json") for item in value]
    else:
        payload = value
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)


def _add_json(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--json", action="store_true", help="输出机器可读 JSON")


def _add_profile(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--profile", type=Path, help="显式 runtime profile 路径")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="easydesign",
        description="EasyDesign 可追溯 binder 设计流程（Developer Preview）",
    )
    parser.add_argument("--version", action="version", version=easydesign.__version__)
    parser.add_argument("--debug", action="store_true", help="失败时显示完整 traceback")
    commands = parser.add_subparsers(dest="command", required=True)

    setup_parser = commands.add_parser(
        "setup",
        help="在当前仓库 runtime/ 内安装 EasyDesign 环境与资产",
    )
    setup_action = setup_parser.add_mutually_exclusive_group()
    setup_action.add_argument("--plan", action="store_true", help="只显示计划，不写入")
    setup_action.add_argument(
        "--detach",
        action="store_true",
        help="持久后台安装；关闭 SSH 或浏览器不会中断",
    )
    setup_action.add_argument(
        "--status",
        action="store_true",
        help="只读取最近安装任务状态",
    )
    setup_scope = setup_parser.add_mutually_exclusive_group()
    setup_scope.add_argument("--minimal", action="store_true", help="仅安装 core/UI")
    setup_scope.add_argument(
        "--component",
        choices=SETUP_COMPONENT_IDS,
        help="只安装一个后端及其必需资产",
    )
    setup_parser.add_argument(
        "--accept-license",
        action="append",
        default=[],
        metavar="ASSET_ID",
        help="确认一个运行资产的许可；可重复提供",
    )
    setup_parser.add_argument("--conda", type=Path, help="显式 Conda executable")
    setup_parser.add_argument(
        "--pip-index-url",
        default="https://pypi.org/simple",
        help="只用于本次安装子进程的 HTTPS Python package index",
    )
    setup_parser.add_argument(
        "--job-id",
        help="与 --status 一起查看一个安装任务",
    )
    _add_json(setup_parser)

    env_parser = commands.add_parser("env", help="查看仓库内环境注册状态")
    env_commands = env_parser.add_subparsers(dest="env_command", required=True)
    env_status_parser = env_commands.add_parser("status", help="显示七个环境的状态")
    _add_json(env_status_parser)

    assets_parser = commands.add_parser("assets", help="查看仓库内模型和资产状态")
    assets_commands = assets_parser.add_subparsers(dest="assets_command", required=True)
    assets_status_parser = assets_commands.add_parser("status", help="显示运行资产状态")
    _add_json(assets_status_parser)

    workspace_parser = commands.add_parser("workspace", help="管理仓库内运行工作区")
    workspace_commands = workspace_parser.add_subparsers(
        dest="workspace_command",
        required=True,
    )
    import_legacy_parser = workspace_commands.add_parser(
        "import-legacy",
        help="复制旧部署证据并按新锁重建；不会改动原目录",
    )
    import_legacy_parser.add_argument("--profile", type=Path, required=True)
    import_legacy_parser.add_argument("--env-root", type=Path, required=True)
    _add_json(import_legacy_parser)

    init_parser = commands.add_parser("init", help="从真实 target 创建最小用户项目")
    init_parser.add_argument("project_dir", type=Path)
    init_source = init_parser.add_mutually_exclusive_group(required=True)
    init_source.add_argument("--target", type=Path)
    init_source.add_argument("--target-bundle", type=Path)
    init_source.add_argument("--pdb-id")
    init_source.add_argument("--uniprot")
    init_source.add_argument("--uniprot-query")
    init_parser.add_argument("--source-run-root", type=Path)
    init_parser.add_argument("--chain")
    init_parser.add_argument(
        "--chain-namespace",
        choices=("auth", "label"),
        default="auth",
    )
    init_parser.add_argument("--identity-uniprot")
    init_parser.add_argument("--taxon-id", type=int)
    init_parser.add_argument("--project-id")
    init_parser.add_argument("--target-id")
    init_parser.add_argument(
        "--execution-mode",
        choices=("review-gated", "unattended"),
        default="review-gated",
    )
    init_parser.add_argument(
        "--scope-range",
        help="UniProt/reference residue range，例如 25:646",
    )
    init_parser.add_argument(
        "--scope-feature-type",
        choices=("Domain", "Chain", "Topological domain"),
    )
    init_parser.add_argument("--scope-feature-name")
    init_parser.add_argument(
        "--precomputed-msa",
        type=Path,
        help="显式提供与 target query 完全一致的 A3M；不会调用远程 MSA",
    )
    init_parser.add_argument(
        "--msa-cache-mode",
        choices=("online", "prefer-cache", "offline"),
        default="online",
        help="远程 MSA 缓存策略；默认 online 每次刷新",
    )
    init_parser.add_argument(
        "--stop-after",
        type=int,
        choices=(1, 2, 3, 4, 5, 6, 7),
        default=1,
    )
    init_parser.add_argument(
        "--stage02-method",
        choices=("sasa", "scannet", "both"),
        default=None,
        help="Stage 02 自动方法（review-gated 默认 both；unattended 默认 sasa）",
    )
    _add_json(init_parser)

    profile_parser = commands.add_parser("profile", help="管理本机 runtime profile")
    profile_commands = profile_parser.add_subparsers(dest="profile_command", required=True)
    profile_init = profile_commands.add_parser("init", help="创建空 backend profile")
    profile_init.add_argument("--path", type=Path)
    profile_init.add_argument("--profile-id", default="local")
    profile_init.add_argument("--runs-root", type=Path)
    profile_show = profile_commands.add_parser("show", help="显示已解析 profile")
    profile_show.add_argument("--path", type=Path)
    _add_json(profile_show)
    profile_validate = profile_commands.add_parser("validate", help="只验证 profile schema")
    profile_validate.add_argument("--path", type=Path)
    _add_json(profile_validate)

    config_parser = commands.add_parser("config", help="检查用户运行配置")
    config_commands = config_parser.add_subparsers(dest="config_command", required=True)
    config_validate = config_commands.add_parser("validate", help="验证 YAML，不创建 run")
    config_validate.add_argument("config", type=Path)
    _add_profile(config_validate)
    config_validate.add_argument("--runs-root", type=Path)
    _add_json(config_validate)
    config_migrate = config_commands.add_parser(
        "migrate",
        help="将旧 YAML 显式迁移为 canonical 0.7",
    )
    config_migrate.add_argument("config", type=Path)
    config_migrate.add_argument("--output", type=Path, required=True)

    doctor_parser = commands.add_parser("doctor", help="检查本次运行所需环境")
    doctor_parser.add_argument("--config", type=Path)
    _add_profile(doctor_parser)
    doctor_parser.add_argument("--runs-root", type=Path)
    doctor_parser.add_argument(
        "--full",
        action="store_true",
        help="要求并探测全部本地科学后端；任一未就绪即返回失败",
    )
    _add_json(doctor_parser)

    run_parser = commands.add_parser("run", help="执行 YAML 声明的已实现阶段")
    run_parser.add_argument("config", type=Path)
    _add_profile(run_parser)
    run_parser.add_argument("--runs-root", type=Path)
    run_parser.add_argument("--run-id")
    run_parser.add_argument(
        "--from-run",
        type=Path,
        help="从 checksum 验证通过的终态上游 run 建立 continuation",
    )
    run_parser.add_argument("--dry-run", action="store_true")
    _add_json(run_parser)

    remote_parser = commands.add_parser(
        "remote",
        help="通过显式 SSH executor 探测、提交和查看整个 EasyDesign run",
    )
    remote_commands = remote_parser.add_subparsers(
        dest="remote_command",
        required=True,
    )
    remote_list = remote_commands.add_parser(
        "list",
        help="列出 profile 中的远端和控制端已知任务",
    )
    _add_profile(remote_list)
    _add_json(remote_list)
    remote_probe = remote_commands.add_parser("probe", help="只读检查远端运行环境")
    remote_probe.add_argument("executor_id")
    _add_profile(remote_probe)
    _add_json(remote_probe)
    remote_submit = remote_commands.add_parser(
        "submit",
        help="校验并复制上游 run，在远端 systemd worker 中启动 continuation",
    )
    remote_submit.add_argument("executor_id")
    remote_submit.add_argument("--job-id", required=True)
    remote_submit.add_argument("--run-id", required=True)
    remote_submit.add_argument("--config", type=Path, required=True)
    remote_source = remote_submit.add_mutually_exclusive_group(required=True)
    remote_source.add_argument("--from-run", type=Path)
    remote_source.add_argument(
        "--project-root",
        type=Path,
        help="从 Stage 01 开始时复制包含 config/inputs 的项目目录",
    )
    _add_profile(remote_submit)
    _add_json(remote_submit)
    managed_submit = remote_commands.add_parser(
        "submit-managed",
        help="把 Stage 03 或 Stage 05 的 manifest 闭包提交到 Suzhou2 中央队列",
    )
    managed_submit.add_argument("executor_id")
    managed_submit.add_argument("--controller-id", required=True)
    managed_submit.add_argument("--job-id", required=True)
    managed_submit.add_argument("--run-id", required=True)
    managed_submit.add_argument("--config", type=Path, required=True)
    managed_submit.add_argument("--from-run", type=Path, required=True)
    managed_submit.add_argument("--maximum-gpus", type=int)
    managed_submit.add_argument(
        "--sync-mode", choices=("metadata", "review", "complete"), default="review"
    )
    _add_profile(managed_submit)
    _add_json(managed_submit)
    remote_status = remote_commands.add_parser("status", help="查询远端 worker 状态")
    remote_status.add_argument("executor_id")
    remote_status.add_argument("job_id")
    _add_profile(remote_status)
    _add_json(remote_status)
    remote_watch = remote_commands.add_parser(
        "watch",
        help="持续读取远端 worker 和结构化运行进度",
    )
    remote_watch.add_argument("executor_id")
    remote_watch.add_argument("job_id")
    remote_watch.add_argument("--interval", type=float, default=15.0)
    remote_watch.add_argument("--once", action="store_true")
    remote_watch.add_argument("--sync-to", type=Path)
    remote_watch.add_argument(
        "--sync-mode",
        choices=("metadata", "review", "complete"),
        default="review",
    )
    _add_profile(remote_watch)
    _add_json(remote_watch)
    remote_resume = remote_commands.add_parser(
        "resume",
        help="为已停止的远端 run 创建新的持久恢复 worker",
    )
    remote_resume.add_argument("executor_id")
    remote_resume.add_argument("job_id")
    _add_profile(remote_resume)
    _add_json(remote_resume)
    remote_sync = remote_commands.add_parser(
        "sync",
        help="按远端 manifest 增量同步只读运行镜像",
    )
    remote_sync.add_argument("executor_id")
    remote_sync.add_argument("job_id")
    remote_sync.add_argument("--to", type=Path, required=True)
    remote_sync.add_argument(
        "--mode",
        choices=("metadata", "review", "complete"),
        default="review",
    )
    _add_profile(remote_sync)
    _add_json(remote_sync)
    remote_adopt = remote_commands.add_parser(
        "adopt-scale",
        help="校验并引用远端 Stage 06 population，不复制候选文件",
    )
    remote_adopt.add_argument("executor_id")
    remote_adopt.add_argument("--local-run", type=Path, required=True)
    remote_adopt.add_argument("--remote-run-root", type=Path, required=True)
    remote_adopt.add_argument("--continuation-id", required=True)
    _add_profile(remote_adopt)
    _add_json(remote_adopt)

    remote_pair_scan = remote_commands.add_parser(
        "pair-scan", help="读取 Suzhou2 host fingerprint，不保存配对"
    )
    remote_pair_scan.add_argument("--host", required=True)
    remote_pair_scan.add_argument("--port", type=int, default=22)
    _add_json(remote_pair_scan)
    remote_pair_begin = remote_commands.add_parser(
        "pair-begin", help="确认 host fingerprint 并创建当前工作区专用 SSH key"
    )
    remote_pair_begin.add_argument("executor_id")
    remote_pair_begin.add_argument("--controller-id", required=True)
    remote_pair_begin.add_argument("--host", required=True)
    remote_pair_begin.add_argument("--port", type=int, default=22)
    remote_pair_begin.add_argument("--user", default="root")
    remote_pair_begin.add_argument("--confirm-fingerprint", required=True)
    _add_json(remote_pair_begin)
    remote_pair_confirm = remote_commands.add_parser(
        "pair-confirm", help="在远端安装公钥后验证 worker 并完成配对"
    )
    remote_pair_confirm.add_argument("executor_id")
    _add_profile(remote_pair_confirm)
    _add_json(remote_pair_confirm)
    remote_unpair = remote_commands.add_parser(
        "unpair", help="逻辑解绑；保留私钥、远端公钥和历史证据"
    )
    remote_unpair.add_argument("executor_id")
    remote_unpair.add_argument("--confirmed", action="store_true")
    _add_json(remote_unpair)

    hotspots_parser = commands.add_parser(
        "hotspots",
        help="导出或批准 Stage 02 完整候选区域",
    )
    hotspots_commands = hotspots_parser.add_subparsers(
        dest="hotspots_command",
        required=True,
    )
    hotspots_export = hotspots_commands.add_parser(
        "export",
        help="导出人工审批模板，不修改 run",
    )
    hotspots_export.add_argument("run", type=Path)
    hotspots_export.add_argument(
        "--method",
        choices=("sasa", "scannet"),
        help="automatic 双方法时必填；用户提供区域不填写",
    )
    hotspots_export.add_argument("--output", type=Path, required=True)
    hotspots_approve = hotspots_commands.add_parser(
        "approve",
        help="验证审批文件并发布 hotspots.yaml",
    )
    hotspots_approve.add_argument("run", type=Path)
    hotspots_approve.add_argument("--input", type=Path, required=True)

    decisions_parser = commands.add_parser(
        "decisions",
        help="查看、导出或批准任意 Stage 的科学选择门",
    )
    decision_commands = decisions_parser.add_subparsers(
        dest="decisions_command",
        required=True,
    )
    decision_show = decision_commands.add_parser("show", help="显示当前 pending gate")
    decision_show.add_argument("run", type=Path)
    _add_json(decision_show)
    decision_export = decision_commands.add_parser("export", help="导出审批模板")
    decision_export.add_argument("run", type=Path)
    decision_export.add_argument("--output", type=Path, required=True)
    decision_approve = decision_commands.add_parser("approve", help="验证并记录人工决定")
    decision_approve.add_argument("run", type=Path)
    decision_approve.add_argument("--input", type=Path, required=True)
    _add_profile(decision_approve)

    runs_parser = commands.add_parser("runs", help="从 run-index 查看运行")
    runs_commands = runs_parser.add_subparsers(dest="runs_command", required=True)
    runs_list = runs_commands.add_parser("list", help="列出 index 声明的 runs")
    _add_profile(runs_list)
    runs_list.add_argument("--runs-root", type=Path)
    _add_json(runs_list)
    runs_show = runs_commands.add_parser("show", help="验证并显示一个 run")
    runs_show.add_argument("run")
    _add_profile(runs_show)
    runs_show.add_argument("--runs-root", type=Path)
    _add_json(runs_show)
    runs_watch = runs_commands.add_parser(
        "watch",
        help="只读取原子 progress 与事件快照显示当前运行",
    )
    runs_watch.add_argument("run", type=Path)
    runs_watch.add_argument("--interval", type=float, default=5.0)
    runs_watch.add_argument("--once", action="store_true")
    _add_json(runs_watch)
    runs_resume = runs_commands.add_parser(
        "resume",
        help="验证 runtime state 后只恢复未达标任务",
    )
    runs_resume.add_argument("run", type=Path)
    _add_profile(runs_resume)
    _add_json(runs_resume)

    projects_parser = commands.add_parser(
        "projects",
        help="查看、归档或恢复运行索引声明的项目",
    )
    projects_commands = projects_parser.add_subparsers(
        dest="projects_command",
        required=True,
    )
    projects_list = projects_commands.add_parser("list", help="列出项目目录")
    _add_profile(projects_list)
    projects_list.add_argument("--runs-root", type=Path)
    projects_list.add_argument("--include-archived", action="store_true")
    projects_list.add_argument("--include-developer-smoke", action="store_true")
    _add_json(projects_list)
    projects_archive = projects_commands.add_parser(
        "archive",
        help="将终态项目移动到可恢复归档，不改写科学文件",
    )
    projects_archive.add_argument("project_id")
    _add_profile(projects_archive)
    projects_archive.add_argument("--runs-root", type=Path)
    _add_json(projects_archive)
    projects_restore = projects_commands.add_parser(
        "restore",
        help="将归档项目恢复到普通项目目录",
    )
    projects_restore.add_argument("project_id")
    _add_profile(projects_restore)
    projects_restore.add_argument("--runs-root", type=Path)
    _add_json(projects_restore)
    projects_select_primary = projects_commands.add_parser(
        "select-primary",
        help="指定项目首页展示的运行，不修改科学结果",
    )
    projects_select_primary.add_argument("project_id")
    projects_select_primary.add_argument("--run-id", required=True)
    _add_profile(projects_select_primary)
    projects_select_primary.add_argument("--runs-root", type=Path)
    _add_json(projects_select_primary)
    projects_prune_empty = projects_commands.add_parser(
        "prune-empty",
        help="只清理索引已归档项目留下的空一级目录",
    )
    _add_profile(projects_prune_empty)
    projects_prune_empty.add_argument("--runs-root", type=Path)
    _add_json(projects_prune_empty)

    viewer_parser = commands.add_parser("viewer", help="查看自包含结构报告")
    viewer_commands = viewer_parser.add_subparsers(dest="viewer_command", required=True)
    viewer_serve = viewer_commands.add_parser("serve", help="仅在 127.0.0.1 提供已验证报告")
    viewer_serve.add_argument("run", type=Path)
    viewer_serve.add_argument("--port", type=int, default=8000)

    ui_parser = commands.add_parser("ui", help="启动本地产品级科研工作台")
    ui_commands = ui_parser.add_subparsers(dest="ui_command", required=True)
    ui_serve = ui_commands.add_parser("serve", help="仅在 127.0.0.1 启动 React 工作台")
    _add_profile(ui_serve)
    ui_serve.add_argument("--runs-root", type=Path)
    ui_serve.add_argument("--projects-root", type=Path)
    ui_serve.add_argument("--host", choices=("127.0.0.1",), default="127.0.0.1")
    ui_serve.add_argument("--port", type=int, default=18769)
    ui_serve.add_argument("--open", action="store_true", dest="open_browser")
    return parser


def _print_plan(plan: RunPlan) -> None:
    print(f"项目：{plan.project_id}")
    print(f"Target：{plan.target_id}（{plan.detected_input_format}）")
    print(f"执行到 Stage {plan.stop_after_stage}")
    print(f"需要 backend：{', '.join(plan.required_backends)}")
    print(f"Runs：{plan.runs_root}")
    print(f"Profile：{plan.profile_id}")


def _print_diagnostics(report: DiagnosticReport) -> None:
    for check in report.checks:
        print(f"[{check.status}] {check.name}: {check.message}")
    print("环境检查通过。" if report.ok else "环境检查失败。")


def _print_execution(execution: PipelineExecution) -> None:
    if execution.status == "dry-run":
        print("Dry run 通过；未创建任何 run。")
        _print_plan(execution.plan)
        return
    print(f"运行状态：{execution.status}")
    print(f"Run：{execution.run_root}")
    print(f"Run manifest：{execution.run_manifest}")
    if execution.status == "awaiting-human-approval" and execution.run_root is not None:
        print("需要人工选择；下一步：")
        current = (
            load_model(execution.run_manifest, RunManifest)
            if execution.run_manifest is not None
            else None
        )
        if (
            current is not None
            and current.workflow_state is not None
            and current.workflow_state.action == "approve-hotspots"
        ):
            print(
                f"  easydesign hotspots export {execution.run_root} --output hotspots-review.yaml"
            )
            print(
                f"  easydesign hotspots approve {execution.run_root} --input hotspots-review.yaml"
            )
        else:
            print(f"  easydesign decisions show {execution.run_root}")
            print(f"  easydesign decisions export {execution.run_root} --output decision.yaml")
            print(f"  easydesign decisions approve {execution.run_root} --input decision.yaml")
    if execution.viewer_status is not None:
        print(f"Stage 01 Viewer：{execution.viewer_status}")


def _format_setup_plan(payload: dict[str, Any]) -> str:
    def human_bytes(value: int) -> str:
        amount = float(value)
        for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
            if amount < 1024 or unit == "TiB":
                return f"{amount:.1f} {unit}"
            amount /= 1024
        return f"{amount:.1f} TiB"

    lines = [
        "EasyDesign 安装计划",
        f"工作区：{payload['workspace']}",
        f"模式：{payload['mode']}",
        "环境：",
    ]
    if payload.get("component"):
        lines.insert(3, f"组件：{payload['component']}")
    for environment in payload["environments"]:
        lines.append(
            f"- {environment['environment_id']} → {environment['target']} "
            f"(lock {str(environment['lock_sha256'])[:12]}；"
            f"约 {human_bytes(environment['estimated_install_bytes'])})"
        )
    assets = payload["assets"]
    if assets:
        lines.append("运行资产：")
        for asset in assets:
            approval = "需要许可确认" if asset["license_confirmation_required"] else "无需额外确认"
            lines.append(
                f"- {asset['asset_id']}（{asset['license']}；{approval}；"
                f"约 {human_bytes(asset['estimated_install_bytes'])}）"
            )
    disk = payload["disk"]
    lines.extend(
        (
            "磁盘预检：",
            f"- 当前可用：{human_bytes(disk['free_bytes'])}",
            f"- 本次增量峰值估算：{human_bytes(disk['incremental_peak_bytes'])}",
            f"- 安装后安全保留：{human_bytes(disk['reserve_bytes'])}",
            f"- 结论：{'空间满足要求' if disk['sufficient'] else '空间不足，安装将被拒绝'}",
        )
    )
    lines.append("所有写入均限制在 runtime/、projects/、runs/、archives/。")
    lines.append("不会修改系统代理、shell profile、Git 全局配置或 base Conda。")
    return "\n".join(lines)


def _confirmed_setup_licenses(
    payload: dict[str, Any],
    *,
    accepted: set[str],
    allow_prompt: bool,
) -> set[str]:
    """Collect explicit per-asset consent without ever auto-accepting terms."""

    pending = [
        asset
        for asset in payload["assets"]
        if asset["license_confirmation_required"] and asset["asset_id"] not in accepted
    ]
    if not pending or not allow_prompt:
        return accepted
    print("以下运行资产需要在下载前逐项确认许可：")
    for asset in pending:
        answer = (
            input(f"- {asset['asset_id']}（{asset['license']}），确认下载并用于本机运行？[y/N] ")
            .strip()
            .lower()
        )
        if answer in {"y", "yes"}:
            accepted.add(str(asset["asset_id"]))
    return accepted


def _print_setup_summary(summary: BaseModel) -> None:
    payload = summary.model_dump(mode="json")
    print(f"工作区：{payload['workspace']}")
    print(f"安装模式：{payload['mode']}")
    if payload.get("component"):
        print(f"安装组件：{payload['component']}")
    for record in payload["environments"]:
        print(f"[{record['status']}] 环境 {record['environment_id']}")
    for record in payload["assets"]:
        print(f"[{record['status']}] 资产 {record['asset_id']}")
    if payload["awaiting_approval"]:
        print("以下资产仍需明确许可确认：")
        for asset_id in payload["awaiting_approval"]:
            print(f"- {asset_id}")
        component_option = (
            f" --component {payload['component']}" if payload.get("component") else ""
        )
        print(f"确认后重新运行：easydesign setup{component_option} --accept-license ASSET_ID")
    print("安装完成。" if payload["ok"] else "安装尚未完整完成；详情已记录，可安全重试。")


def _format_runtime_status(payload: dict[str, Any]) -> str:
    if "report" in payload:
        return f"旧部署证据已复制：{payload['report']}\n原路径保持不变。"
    key = "environments" if "environments" in payload else "assets"
    lines = [f"工作区：{payload['workspace']}"]
    for item in payload[key]:
        item_id = item.get("environment_id", item.get("asset_id"))
        lines.append(f"[{item['status']}] {item_id}")
    return "\n".join(lines)


def _format_setup_job(payload: BaseModel) -> str:
    values = payload.model_dump(mode="json")
    lines = [
        f"安装任务：{values['job_id']}",
        f"状态：{values['status']}",
        f"组件：{values.get('component') or ('core-ui' if values['minimal'] else 'all')}",
        f"Pip index：{values['pip_index_url']}",
        f"开始时间：{values['started_at']}",
        f"标准输出：{values['stdout_relative_path']}",
        f"错误输出：{values['stderr_relative_path']}",
    ]
    if values.get("completed_at"):
        lines.append(f"完成时间：{values['completed_at']}")
    if values.get("return_code") is not None:
        lines.append(f"退出码：{values['return_code']}")
    if values.get("error"):
        lines.append(f"错误：{values['error']}")
    return "\n".join(lines)


def _runs_root(explicit: Path | None, profile_path: Path | None) -> Path:
    if explicit is not None:
        return explicit.expanduser().resolve()
    selected = profile_path
    if selected is None and not default_runtime_profile_path().is_file():
        return WorkspaceContext.discover().runs_root
    loaded = load_runtime_profile(selected)
    return (
        loaded.profile.runs_root.resolve()
        if loaded.profile.runs_root is not None
        else (Path.cwd() / "runs").resolve()
    )


def _dispatch(arguments: argparse.Namespace) -> int:
    if arguments.command in {"setup", "env", "assets", "workspace"}:
        context = WorkspaceContext.discover()
        if arguments.command == "setup":
            if arguments.status:
                if (
                    arguments.minimal
                    or arguments.component is not None
                    or arguments.accept_license
                    or arguments.conda is not None
                    or arguments.pip_index_url != "https://pypi.org/simple"
                ):
                    raise ConfigurationError("--status 不能与安装范围、许可或 Conda 参数同时使用")
                jobs = (
                    (read_setup_job(context, arguments.job_id),)
                    if arguments.job_id
                    else list_setup_jobs(context)
                )
                if arguments.json:
                    print(_json_text(jobs))
                elif not jobs:
                    print("当前工作区还没有持久安装任务。")
                else:
                    print("\n\n".join(_format_setup_job(job) for job in jobs))
                return 0
            if arguments.job_id is not None:
                raise ConfigurationError("--job-id 只能与 --status 一起使用")
            payload = setup_plan(
                context,
                minimal=arguments.minimal,
                component=arguments.component,
            )
            if arguments.plan:
                print(
                    json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
                    if arguments.json
                    else _format_setup_plan(payload)
                )
                return 0
            accepted_license_ids = _confirmed_setup_licenses(
                payload,
                accepted=set(arguments.accept_license),
                allow_prompt=(not arguments.minimal and not arguments.json and sys.stdin.isatty()),
            )
            if arguments.detach:
                job = launch_setup_job(
                    context,
                    minimal=arguments.minimal,
                    component=arguments.component,
                    accepted_license_ids=accepted_license_ids,
                    conda_executable=arguments.conda,
                    pip_index_url=arguments.pip_index_url,
                )
                if arguments.json:
                    print(_json_text(job))
                else:
                    print(_format_setup_job(job))
                    print(
                        "\n可安全关闭当前 SSH；稍后运行 "
                        f"easydesign setup --status --job-id {job.job_id}"
                    )
                return 0
            summary = setup_workspace(
                context,
                minimal=arguments.minimal,
                component=arguments.component,
                accepted_license_ids=accepted_license_ids,
                conda_executable=arguments.conda,
                pip_index_url=arguments.pip_index_url,
            )
            if arguments.json:
                print(_json_text(summary))
            else:
                _print_setup_summary(summary)
            return 0 if summary.ok else 3
        if arguments.command == "env":
            payload = environment_status(context)
        elif arguments.command == "assets":
            payload = asset_status(context)
        else:
            migration_report = import_legacy_deployment(
                context,
                profile_path=arguments.profile,
                environment_root=arguments.env_root,
            )
            payload = {"status": "imported", "report": str(migration_report)}
        if arguments.json:
            print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
        else:
            print(_format_runtime_status(payload))
        return 0
    if arguments.command == "ui":
        from easydesign.ui import serve_ui

        context = WorkspaceContext.discover()
        serve_ui(
            runs_root=_runs_root(arguments.runs_root, arguments.profile),
            projects_root=(
                context.projects_root
                if arguments.projects_root is None
                else arguments.projects_root
            ),
            profile_path=(context.profile_path if arguments.profile is None else arguments.profile),
            job_root=context.ui_job_root,
            host=arguments.host,
            port=arguments.port,
            open_browser=arguments.open_browser,
        )
        return 0
    if arguments.command == "init":
        scope_range: tuple[int, int] | None = None
        if arguments.scope_range is not None:
            try:
                start_text, end_text = arguments.scope_range.split(":", maxsplit=1)
                scope_range = (int(start_text), int(end_text))
            except (TypeError, ValueError) as error:
                raise ConfigurationError("--scope-range 必须使用 START:END") from error
        initialized = initialize_project(
            project_root=arguments.project_dir,
            target=arguments.target,
            target_bundle=arguments.target_bundle,
            source_run_root=arguments.source_run_root,
            pdb_id=arguments.pdb_id,
            chain=arguments.chain,
            chain_namespace=arguments.chain_namespace,
            identity_uniprot=arguments.identity_uniprot,
            uniprot=arguments.uniprot,
            uniprot_query=arguments.uniprot_query,
            taxon_id=arguments.taxon_id,
            project_id=arguments.project_id,
            target_id=arguments.target_id,
            stop_after_stage=arguments.stop_after,
            stage02_method=arguments.stage02_method,
            execution_mode=arguments.execution_mode,
            scope_range=scope_range,
            scope_feature_type=arguments.scope_feature_type,
            scope_feature_name=arguments.scope_feature_name,
            precomputed_msa=arguments.precomputed_msa,
            msa_cache_mode=arguments.msa_cache_mode,
        )
        init_payload = {
            "project_root": str(initialized.project_root),
            "config": str(initialized.config_path),
            "target": (None if initialized.target_path is None else str(initialized.target_path)),
            "format": str(initialized.detected_format),
            "msa": (None if initialized.msa_path is None else str(initialized.msa_path)),
        }
        if arguments.json:
            print(_json_text(init_payload))
        else:
            print(f"项目已创建：{initialized.project_root}")
            print(f"下一步：easydesign config validate {initialized.config_path}")
        return 0

    if arguments.command == "projects":
        root = _runs_root(arguments.runs_root, arguments.profile)
        if arguments.projects_command == "list":
            entries = list_project_catalog(
                root,
                include_archived=arguments.include_archived,
                include_developer_smoke=arguments.include_developer_smoke,
            )
            projects_payload = [
                {
                    "project_id": entry.project_id,
                    "category": entry.category,
                    "run_count": entry.run_count,
                    "paths": list(entry.paths),
                }
                for entry in entries
            ]
            if arguments.json:
                print(
                    json.dumps(
                        projects_payload,
                        ensure_ascii=False,
                        indent=2,
                        sort_keys=True,
                    )
                )
            else:
                for entry in entries:
                    print(f"{entry.project_id}: {entry.category}, {entry.run_count} 个运行")
            return 0
        if arguments.projects_command == "select-primary":
            selected = select_project_primary_run(
                root,
                project_id=arguments.project_id,
                run_id=arguments.run_id,
            )
            selected_payload = {
                "project_id": selected.project_id,
                "run_id": selected.run_id,
                "path": selected.path,
                "index_path": str(selected.index_path),
            }
            if arguments.json:
                print(
                    json.dumps(
                        selected_payload,
                        ensure_ascii=False,
                        indent=2,
                        sort_keys=True,
                    )
                )
            else:
                print(f"项目首页已改为展示：{selected.project_id}/{selected.run_id}")
            return 0
        if arguments.projects_command == "prune-empty":
            removed = prune_archived_project_shells(root)
            prune_payload = {"removed_project_shells": list(removed)}
            if arguments.json:
                print(
                    json.dumps(
                        prune_payload,
                        ensure_ascii=False,
                        indent=2,
                        sort_keys=True,
                    )
                )
            elif removed:
                print("已清理归档空项目目录：")
                for project_id in removed:
                    print(f"- {project_id}")
            else:
                print("没有可安全清理的归档空项目目录。")
            return 0
        project_outcome = (
            archive_project(root, arguments.project_id)
            if arguments.projects_command == "archive"
            else restore_project(root, arguments.project_id)
        )
        project_payload = {
            "project_id": project_outcome.project_id,
            "category": project_outcome.category,
            "moved_paths": [list(item) for item in project_outcome.moved_paths],
            "index_path": str(project_outcome.index_path),
        }
        if arguments.json:
            print(json.dumps(project_payload, ensure_ascii=False, indent=2, sort_keys=True))
        else:
            action = "已归档" if arguments.projects_command == "archive" else "已恢复"
            print(f"项目{action}：{project_outcome.project_id}")
            for source, destination in project_outcome.moved_paths:
                print(f"- {source} → {destination}")
        return 0

    if arguments.command == "profile":
        if arguments.profile_command == "init":
            path = initialize_runtime_profile(
                arguments.path,
                profile_id=arguments.profile_id,
                runs_root=arguments.runs_root,
            )
            print(f"Runtime profile 已创建：{path}")
            print("请显式填写本机 backend 绝对路径，然后运行 easydesign profile validate。")
            return 0
        loaded = load_runtime_profile(arguments.path)
        if arguments.profile_command == "show":
            if arguments.json:
                print(_json_text(loaded.profile))
            else:
                print(f"Profile：{loaded.path}")
                print(_json_text(loaded.profile))
            return 0
        payload = {
            "status": "valid",
            "path": str(loaded.path),
            "profile_id": loaded.profile.profile_id,
            "sha256": loaded.identity.sha256,
        }
        print(_json_text(payload) if arguments.json else f"Profile 校验通过：{loaded.path}")
        return 0

    if arguments.command == "config":
        if arguments.config_command == "migrate":
            migrated = migrate_run_configuration(
                arguments.config,
                arguments.output,
            )
            print(f"配置已迁移：{migrated}")
            return 0
        plan = validate_run_configuration(
            arguments.config,
            profile_path=arguments.profile,
            runs_root=arguments.runs_root,
        )
        if arguments.json:
            print(_json_text(plan))
        else:
            _print_plan(plan)
            print("配置校验通过；未创建 run。")
        return 0

    if arguments.command == "doctor":
        report = diagnose_runtime(
            profile_path=arguments.profile,
            config_path=arguments.config,
            runs_root=arguments.runs_root,
            full=arguments.full,
        )
        if arguments.json:
            print(_json_text(report))
        else:
            _print_diagnostics(report)
        return 0 if report.ok else 3

    if arguments.command == "run":
        execution = execute_pipeline(
            arguments.config,
            profile_path=arguments.profile,
            runs_root=arguments.runs_root,
            run_id=arguments.run_id,
            dry_run=arguments.dry_run,
            continue_from_run=arguments.from_run,
        )
        if arguments.json:
            print(_json_text(execution))
        else:
            _print_execution(execution)
        return 0

    if arguments.command == "remote":
        if arguments.remote_command == "pair-scan":
            identity = scan_host_identity(host=arguments.host, port=arguments.port)
            rendered = (
                _json_text(identity)
                if arguments.json
                else f"Host fingerprint: {identity.fingerprint}"
            )
            print(rendered)
            return 0
        if arguments.remote_command == "pair-begin":
            pairing_record = RemoteExecutorRegistry().begin_pairing(
                executor_id=arguments.executor_id,
                controller_id=arguments.controller_id,
                host=arguments.host,
                port=arguments.port,
                user=arguments.user,
                confirmed_host_fingerprint=arguments.confirm_fingerprint,
            )
            payload = pairing_record.model_dump(mode="json")
            payload["public_key_install_command"] = public_key_install_command(pairing_record)
            rendered = (
                _json_text(payload)
                if arguments.json
                else json.dumps(payload, ensure_ascii=False, indent=2)
            )
            print(rendered)
            return 0
        if arguments.remote_command == "pair-confirm":
            waiting = RemoteExecutorRegistry().latest(arguments.executor_id)
            if waiting is None or waiting.state != "awaiting-public-key":
                raise ConfigurationError("executor 不处于等待确认状态")
            # Probe with the waiting record before publishing the paired revision.
            # active_runtimes intentionally excludes waiting records, so use the
            # same strict connection construction locally without persisting it.
            import shutil

            from easydesign.backends.executors import SshRemoteExecutor
            from easydesign.orchestration.profile import SshRemoteRuntime
            from easydesign.orchestration.remote_execution import _connection

            managed_root = Path(waiting.managed_worker_root)
            probe_executor = SshRemoteExecutor(
                _connection(
                    waiting.executor_id,
                    SshRemoteRuntime(
                        host=waiting.host,
                        user=waiting.user,
                        port=waiting.port,
                        identity_file=waiting.identity_file,
                        known_hosts_file=waiting.known_hosts_file,
                        ssh_executable=Path(shutil.which("ssh") or "/usr/bin/ssh"),
                        rsync_executable=Path(shutil.which("rsync") or "/usr/bin/rsync"),
                        remote_work_root=managed_root,
                        remote_runs_root=managed_root / "runs",
                        remote_easydesign_executable=managed_root / "service/easydesign",
                        remote_profile=managed_root / "config/profile.yaml",
                    ),
                )
            )
            managed_worker_probe = ManagedWorkerProbe.model_validate(
                probe_executor.managed_worker_json("probe")
            )
            require_managed_probe_compatible(managed_worker_probe)
            paired = RemoteExecutorRegistry().mark_paired(arguments.executor_id)
            payload = {
                "pairing": paired.model_dump(mode="json"),
                "probe": managed_worker_probe.model_dump(mode="json"),
            }
            rendered = (
                _json_text(payload)
                if arguments.json
                else json.dumps(payload, ensure_ascii=False, indent=2)
            )
            print(rendered)
            return 0
        if arguments.remote_command == "unpair":
            if not arguments.confirmed:
                raise ConfigurationError("逻辑解绑需要 --confirmed")
            unpaired_record = RemoteExecutorRegistry().unpair(arguments.executor_id)
            print(
                _json_text(unpaired_record)
                if arguments.json
                else f"已逻辑解绑：{unpaired_record.executor_id}"
            )
            return 0
        if arguments.remote_command == "list":
            executor_ids = list_remote_executor_ids(profile_path=arguments.profile)
            records = list_remote_job_records()
            managed_records = list_managed_remote_submissions()
            remote_list_payload = {
                "executors": list(executor_ids),
                "jobs": [item.model_dump(mode="json") for item in records],
                "managed_jobs": [item.model_dump(mode="json") for item in managed_records],
            }
            if arguments.json:
                print(_json_text(remote_list_payload))
            else:
                print("可用远端：")
                for executor_id in executor_ids:
                    print(f"- {executor_id}")
                print("已知任务：")
                for remote_job_record in records:
                    remote_submission = remote_job_record.submission
                    print(
                        f"- {remote_submission.executor_id}/{remote_submission.job_id}: "
                        f"{remote_submission.project_id}/{remote_submission.run_id} "
                        f"(resume={remote_job_record.resume_count})"
                    )
                for managed_submission in managed_records:
                    print(
                        f"- {managed_submission.executor_id}/{managed_submission.job_id}: "
                        f"{managed_submission.project_id}/{managed_submission.run_id} "
                        f"(managed queue={managed_submission.queue_status})"
                    )
            return 0
        if arguments.remote_command == "probe":
            pairing = RemoteExecutorRegistry().latest(arguments.executor_id)
            if pairing is not None and pairing.state == "paired":
                managed_probe = probe_managed_executor(
                    executor_id=arguments.executor_id,
                    profile_path=arguments.profile,
                )
                if arguments.json:
                    print(_json_text(managed_probe))
                else:
                    print(f"Manager：{managed_probe.manager_version}")
                    print(f"EasyDesign：{managed_probe.easydesign_version}")
                    print(f"GPU：{managed_probe.gpu_count}")
                    print(f"队列：{managed_probe.queue_depth}")
                    print(
                        f"数据盘可用：{managed_probe.filesystem_available_bytes / 1024**3:.1f} GiB"
                    )
                return 0
            legacy_probe = probe_remote_executor(
                executor_id=arguments.executor_id,
                profile_path=arguments.profile,
            )
            if arguments.json:
                print(_json_text(legacy_probe))
            else:
                print(f"远端主机：{legacy_probe.hostname}")
                print(f"EasyDesign：{legacy_probe.easydesign_version}")
                print(f"GPU：{legacy_probe.gpu_count}")
                print(f"运行盘可用：{legacy_probe.filesystem_available_bytes / 1024**3:.1f} GiB")
            return 0
        if arguments.remote_command == "adopt-scale":
            continuation = adopt_remote_scale_evidence(
                local_run_root=arguments.local_run,
                remote_run_root=arguments.remote_run_root,
                executor_id=arguments.executor_id,
                continuation_id=arguments.continuation_id,
                profile_path=arguments.profile,
            )
            if arguments.json:
                print(_json_text(continuation))
            else:
                print(
                    "Stage 06 远端证据已采用："
                    f"{continuation.execution.candidate_count:,} 个候选，"
                    f"{continuation.execution.shard_count} 个分片"
                )
                print("旧 Stage 05 scientific-stop 保持不变；Stage 07 需在远端后端探针通过后启动。")
            return 0
        if arguments.remote_command == "submit":
            remote_submission = submit_remote_pipeline(
                executor_id=arguments.executor_id,
                job_id=arguments.job_id,
                run_id=arguments.run_id,
                config_path=arguments.config,
                source_run=arguments.from_run,
                project_root=arguments.project_root,
                profile_path=arguments.profile,
            )
            if arguments.json:
                print(_json_text(remote_submission))
            else:
                print(f"远端任务已提交：{remote_submission.unit_name}")
                print(f"远端 run：{remote_submission.remote_run_root}")
                print(
                    "查看状态："
                    f"easydesign remote status {remote_submission.executor_id} "
                    f"{remote_submission.job_id}"
                )
            return 0
        if arguments.remote_command == "submit-managed":
            managed_submission = submit_managed_pipeline(
                executor_id=arguments.executor_id,
                controller_id=arguments.controller_id,
                job_id=arguments.job_id,
                run_id=arguments.run_id,
                config_path=arguments.config,
                source_run=arguments.from_run,
                profile_path=arguments.profile,
                maximum_gpus=arguments.maximum_gpus,
                sync_mode=arguments.sync_mode,
            )
            if arguments.json:
                print(_json_text(managed_submission))
            else:
                print(f"Suzhou2 任务已入队：{managed_submission.job_id}")
                print(f"阶段：{managed_submission.stage_range}")
                print(f"候选预算：{managed_submission.candidate_budget:,}")
            return 0
        if arguments.remote_command == "watch":
            if arguments.interval <= 0 or arguments.interval > 60:
                raise ConfigurationError("--interval 必须在 0 到 60 秒之间")
            while True:
                watched_managed_submission = next(
                    (
                        item
                        for item in list_managed_remote_submissions(
                            executor_id=arguments.executor_id
                        )
                        if item.job_id == arguments.job_id
                    ),
                    None,
                )
                if watched_managed_submission is not None:
                    managed_observation = observe_managed_pipeline(
                        executor_id=arguments.executor_id,
                        job_id=arguments.job_id,
                        profile_path=arguments.profile,
                    )
                    if arguments.json:
                        print(_json_text(managed_observation), flush=True)
                    else:
                        managed_queue_revision = managed_observation.queue
                        print(
                            f"[{managed_observation.checked_at.isoformat()}] "
                            f"{arguments.executor_id}/{arguments.job_id} "
                            + (
                                "远程连接暂时中断"
                                if managed_queue_revision is None
                                else (
                                    f"queue={managed_queue_revision.status} "
                                    f"devices={managed_queue_revision.assigned_devices}"
                                )
                            ),
                            flush=True,
                        )
                    terminal = (
                        managed_observation.queue is not None
                        and managed_observation.queue.status in {"succeeded", "failed"}
                    )
                    if arguments.once or terminal:
                        return 0
                    time.sleep(arguments.interval)
                    continue
                remote_observation = observe_remote_pipeline(
                    executor_id=arguments.executor_id,
                    job_id=arguments.job_id,
                    profile_path=arguments.profile,
                )
                sync_report = None
                if arguments.sync_to is not None:
                    sync_report = sync_remote_pipeline(
                        executor_id=arguments.executor_id,
                        job_id=arguments.job_id,
                        destination=arguments.sync_to,
                        mode=arguments.sync_mode,
                        profile_path=arguments.profile,
                    )
                if arguments.json:
                    observation_payload: dict[str, Any] = remote_observation.model_dump(mode="json")
                    observation_payload["sync"] = (
                        None if sync_report is None else sync_report.model_dump(mode="json")
                    )
                    print(_json_text(observation_payload), flush=True)
                else:
                    worker = remote_observation.worker
                    print(
                        f"[{remote_observation.checked_at.isoformat()}] "
                        f"{remote_observation.executor_id}/{remote_observation.job_id} "
                        f"worker={worker.active_state}/{worker.sub_state}",
                        flush=True,
                    )
                    if remote_observation.progress is not None:
                        progress = remote_observation.progress
                        print(
                            f"  {progress.stage_id}: tasks "
                            f"{progress.succeeded_tasks}/{progress.total_tasks}, "
                            f"running={progress.running_tasks}, "
                            f"failed={progress.failed_tasks}; candidates "
                            f"{progress.collected_candidates}/"
                            f"{progress.planned_candidates}",
                            flush=True,
                        )
                        for heartbeat in progress.task_heartbeats:
                            print(
                                f"  HEARTBEAT GPU {heartbeat.device} "
                                f"{heartbeat.task_id}: "
                                f"{heartbeat.elapsed_seconds / 60:.1f} min",
                                flush=True,
                            )
                    elif remote_observation.progress_error is not None:
                        print(
                            f"  进度暂不可用：{remote_observation.progress_error}",
                            flush=True,
                        )
                    if sync_report is not None:
                        print(
                            f"  镜像已同步：{sync_report.destination} "
                            f"({sync_report.file_count} files)",
                            flush=True,
                        )
                progress_terminal = (
                    remote_observation.progress is not None
                    and remote_observation.progress.status
                    in {"succeeded", "scientific-stop", "failed", "incomplete"}
                )
                worker_terminal = remote_observation.worker.active_state in {
                    "failed",
                    "inactive",
                }
                if arguments.once or progress_terminal or worker_terminal:
                    return 0
                time.sleep(arguments.interval)
        if arguments.remote_command == "resume":
            resumed_managed_submission = next(
                (
                    item
                    for item in list_managed_remote_submissions(executor_id=arguments.executor_id)
                    if item.job_id == arguments.job_id
                ),
                None,
            )
            if resumed_managed_submission is not None:
                managed_resume_observation = observe_managed_pipeline(
                    executor_id=arguments.executor_id,
                    job_id=arguments.job_id,
                    profile_path=arguments.profile,
                )
                if managed_resume_observation.queue is None:
                    raise ConfigurationError("远程连接暂时中断；远程任务不标记失败")
                if managed_resume_observation.queue.status == "failed":
                    print(
                        "受管 worker 会在 maximum_attempts 范围内自动重试，"
                        "无需创建第二个 shell worker。"
                    )
                else:
                    print(f"当前队列状态：{managed_resume_observation.queue.status}")
                return 0
            resumed_remote_record = resume_remote_pipeline(
                executor_id=arguments.executor_id,
                job_id=arguments.job_id,
                profile_path=arguments.profile,
            )
            if arguments.json:
                print(_json_text(resumed_remote_record))
            else:
                print(f"远端恢复 worker 已提交：{resumed_remote_record.active_unit_name}")
                print(f"恢复次数：{resumed_remote_record.resume_count}")
                print(f"远端 run：{resumed_remote_record.submission.remote_run_root}")
            return 0
        if arguments.remote_command == "sync":
            sync_result = sync_remote_pipeline(
                executor_id=arguments.executor_id,
                job_id=arguments.job_id,
                destination=arguments.to,
                mode=arguments.mode,
                profile_path=arguments.profile,
            )
            if arguments.json:
                print(_json_text(sync_result))
            else:
                print(f"远端镜像：{sync_result.destination}")
                print(f"同步文件：{sync_result.file_count}")
                print(f"同步大小：{sync_result.size_bytes / 1024**2:.1f} MiB")
                print(
                    "完整嵌套 artifact："
                    f"{'是' if sync_result.completed_artifact_closure else '否（元数据模式）'}"
                )
            return 0
        status_managed_submission = next(
            (
                item
                for item in list_managed_remote_submissions(executor_id=arguments.executor_id)
                if item.job_id == arguments.job_id
            ),
            None,
        )
        if status_managed_submission is not None:
            managed_status_observation = observe_managed_pipeline(
                executor_id=arguments.executor_id,
                job_id=arguments.job_id,
                profile_path=arguments.profile,
            )
            payload = {
                "submission": status_managed_submission.model_dump(mode="json"),
                "observation": managed_status_observation.model_dump(mode="json"),
            }
            rendered = (
                _json_text(payload)
                if arguments.json
                else json.dumps(payload, ensure_ascii=False, indent=2)
            )
            print(rendered)
            return 0
        remote_submission = read_remote_submission(
            executor_id=arguments.executor_id,
            job_id=arguments.job_id,
        )
        remote_job_record = read_remote_job_record(
            executor_id=arguments.executor_id,
            job_id=arguments.job_id,
        )
        status = read_remote_status(
            executor_id=arguments.executor_id,
            job_id=arguments.job_id,
            profile_path=arguments.profile,
        )
        status_payload: dict[str, Any] = {
            "submission": remote_submission.model_dump(mode="json"),
            "worker": status.model_dump(mode="json"),
        }
        if arguments.json:
            print(_json_text(status_payload))
        else:
            print(f"远端任务：{remote_submission.unit_name}")
            if remote_job_record.active_unit_name != remote_submission.unit_name:
                print(f"当前恢复 worker：{remote_job_record.active_unit_name}")
            print(f"Worker：{status.active_state}/{status.sub_state}")
            print(f"退出码：{status.exec_main_status}")
            print(f"远端 run：{remote_submission.remote_run_root}")
        return 0

    if arguments.command == "hotspots":
        if arguments.hotspots_command == "export":
            method = (
                None
                if arguments.method is None
                else (
                    RegionMethod.SASA_SURFACE_DIVERSITY
                    if arguments.method == "sasa"
                    else RegionMethod.SCANNET_EPITOPE_NO_MSA
                )
            )
            output = export_hotspot_review(
                arguments.run,
                method=method,
                output=arguments.output,
            )
            print(f"Hotspot 审批模板已导出：{output}")
            print(
                "请填写 approved_by、每个区域的两类理由；用户提供区域和 "
                "structural-only 证据还需分别确认 acknowledgement。"
            )
            return 0
        hotspots = approve_hotspots(
            arguments.run,
            input_path=arguments.input,
        )
        print(f"Stage 02 已批准：{hotspots}")
        return 0

    if arguments.command == "decisions":
        if arguments.decisions_command == "show":
            request = show_decision(arguments.run)
            if arguments.json:
                print(_json_text(request))
            else:
                print(f"Decision：{request.decision_id}")
                print(f"Gate：{request.stage_id}/{request.gate}")
                print(request.message)
                for option in request.options:
                    state = "eligible" if option.eligible else "ineligible"
                    print(f"- {option.option_id} [{state}] {option.label}")
            return 0
        if arguments.decisions_command == "export":
            output = export_decision(arguments.run, output=arguments.output)
            print(f"Decision 审批模板已导出：{output}")
            return 0
        decision_record = approve_decision(arguments.run, input_path=arguments.input)
        print(f"Decision 已记录：{decision_record}")
        execution = continue_pipeline_after_decision(
            arguments.run,
            decision_record=decision_record,
            profile_path=arguments.profile,
        )
        _print_execution(execution)
        return 0

    if arguments.command == "runs":
        if arguments.runs_command == "watch":
            if arguments.interval <= 0 or arguments.interval > 60:
                raise ConfigurationError("--interval 必须在 0 到 60 秒之间")
            while True:
                from easydesign.orchestration import read_pipeline_progress

                progress = read_pipeline_progress(arguments.run)
                if arguments.json:
                    print(_json_text(progress), flush=True)
                else:
                    print(
                        f"[{progress.updated_at.isoformat()}] "
                        f"{progress.stage_id}"
                        f"{f'/{progress.phase}' if progress.phase else ''} "
                        f"{progress.status}: "
                        f"tasks {progress.succeeded_tasks}/{progress.total_tasks}, "
                        f"running={progress.running_tasks}, failed={progress.failed_tasks}; "
                        f"candidates {progress.collected_candidates}/"
                        f"{progress.planned_candidates}",
                        flush=True,
                    )
                    if progress.per_device:
                        assignments = ", ".join(
                            f"GPU {device}={strategy}"
                            for device, strategy in sorted(progress.per_device.items())
                        )
                        print(f"  {assignments}", flush=True)
                    if progress.estimated_remaining_seconds is not None:
                        print(
                            f"  ETA≈{progress.estimated_remaining_seconds / 60:.1f} min",
                            flush=True,
                        )
                    for message in progress.recent_errors[-3:]:
                        print(f"  ERROR {message}", flush=True)
                if arguments.once or progress.status in {
                    "succeeded",
                    "scientific-stop",
                    "failed",
                    "incomplete",
                }:
                    return 0
                time.sleep(arguments.interval)
        if arguments.runs_command == "resume":
            resume_outcome = resume_pipeline(
                arguments.run,
                profile_path=arguments.profile,
            )
            if arguments.json:
                print(_json_text(resume_outcome))
            else:
                print(f"恢复状态：{resume_outcome.status}")
                if isinstance(resume_outcome, Stage04Execution):
                    print(f"完整候选：{resume_outcome.complete_candidate_count}")
                elif isinstance(resume_outcome, Stage05Execution):
                    print(f"胜出策略：{resume_outcome.selected_strategy_id or '无（科学停止）'}")
                elif isinstance(resume_outcome, Stage06Execution):
                    print(f"规模候选：{resume_outcome.complete_candidate_count}")
                elif isinstance(resume_outcome, Stage07Execution):
                    print(
                        f"最终候选：primary={resume_outcome.primary_count}，"
                        f"backup={resume_outcome.backup_count}"
                    )
                print(f"Run：{resume_outcome.run_root}")
            return 4 if resume_outcome.status == "incomplete" else 0
        root = _runs_root(arguments.runs_root, arguments.profile)
        if arguments.runs_command == "list":
            runs = list_runs(root)
            if arguments.json:
                print(_json_text(runs))
            elif not runs:
                print(f"没有 index 声明的 run：{root}")
            else:
                for run in runs:
                    print(
                        f"{run.project_id}/{run.run_id}\t{run.status}\t"
                        f"revision={run.manifest_revision}\t{run.integrity_status}"
                    )
            return 0
        run = show_run(root, arguments.run)
        if arguments.json:
            print(_json_text(run))
        else:
            print(f"Run：{run.project_id}/{run.run_id}")
            print(f"状态：{run.status}")
            print(f"Manifest：{run.latest_manifest}")
            print(f"Stages：{', '.join(run.completed_stages) or '无'}")
        return 0

    if arguments.command == "viewer":
        report_root = resolve_target_viewer_argument(arguments.run)
        server = create_target_viewer_server(report_root, port=arguments.port)
        print(f"Target Viewer report：{server.report_root}")
        print(f"Local URL：{server.url}")
        print(
            "远程服务器请使用 SSH 端口转发："
            f"ssh -N -L {server.server.server_address[1]}:{HOST}:"
            f"{server.server.server_address[1]} <server>"
        )
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            print("\nTarget Viewer server 已停止。")
        finally:
            server.close()
        return 0
    raise AssertionError(f"未处理命令: {arguments.command}")


def _exit_code(error: Exception) -> int:
    if isinstance(error, ConfigurationError):
        return 2
    if isinstance(error, (ArtifactIntegrityError, ArtifactNotFoundError, SerializationError)):
        return 5
    return 4


def main(argv: Sequence[str] | None = None) -> int:
    parser = _parser()
    arguments = parser.parse_args(argv)
    try:
        return _dispatch(arguments)
    except (EasyDesignError, OSError, ValueError) as error:
        if arguments.debug:
            traceback.print_exc()
        else:
            print(f"ERROR: {error}", file=sys.stderr)
        return _exit_code(error)


if __name__ == "__main__":
    raise SystemExit(main())
