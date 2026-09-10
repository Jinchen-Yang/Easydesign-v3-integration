"""EasyDesign Local agent-native research command line."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import traceback
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Literal, cast

import yaml  # type: ignore[import-untyped]
from pydantic import BaseModel

import easydesign
from easydesign.core import ConfigurationError, EasyDesignError, load_model
from easydesign.orchestration.afo_releases import (
    install_stable_afo_if_available,
    load_afo_release_catalog,
    materialize_afo_bundle,
)
from easydesign.orchestration.application import diagnose_runtime
from easydesign.orchestration.gpcr_site import (
    GpcrSiteRequest,
    publish_gpcr_analysis,
    resolve_latest_gpcr_analysis,
    validate_gpcr_analysis_bundle,
)
from easydesign.orchestration.local_project import completed_steps, resolve_project_run
from easydesign.orchestration.miniforge import install_miniforge, miniforge_status
from easydesign.orchestration.openfold3_validation import (
    approve_openfold3_validation_report,
    generate_openfold3_validation_report,
)
from easydesign.orchestration.research import (
    initialize_research_project,
    job_drain,
    job_resume,
    job_status,
    job_watch,
    pilot_interpret,
    pilot_plan,
    pilot_promote,
    pilot_review,
    pilot_run,
    project_status,
    scale_plan,
    scale_run,
    select_plan,
    select_run,
    site_approve,
    site_propose,
    site_scan,
    strategy_draft,
    strategy_freeze,
    strategy_validate,
    target_approve,
    target_prepare,
)
from easydesign.orchestration.research_models import CommandResult, ResearchPhase
from easydesign.orchestration.runtime_components import (
    activate_openfold3_release,
    install_openfold3_component,
    list_openfold3_components,
    runtime_status,
)
from easydesign.orchestration.runtime_setup import (
    SETUP_COMPONENT_ASSETS,
    SETUP_COMPONENT_SEQUENCE,
    asset_status,
    environment_status,
    setup_plan,
    setup_workspace,
)
from easydesign.orchestration.setup_jobs import (
    SetupJobProjection,
    launch_setup_job,
    list_setup_jobs,
    read_setup_job,
)
from easydesign.orchestration.source_policy import SOURCE_POLICIES
from easydesign.reporting import (
    ReviewDashboardPresentationOverride,
    ReviewDashboardReport,
    build_evidence_viewer_payload,
    build_stage02_viewer_overlay,
    create_gpcr_review_server,
    create_review_dashboard_server,
    create_target_viewer_server,
    export_gpcr_review_report,
    export_review_dashboard,
    generate_gpcr_review_report,
    generate_review_dashboard,
    resolve_latest_gpcr_review_report,
    resolve_latest_review_dashboard,
    resolve_target_viewer_argument,
    validate_gpcr_review_report,
)
from easydesign.workspace_context import WorkspaceContext

LOCAL_RUNTIME_COMPONENTS = SETUP_COMPONENT_SEQUENCE
RUNTIME_PLAN_COMPONENTS = ("all", *LOCAL_RUNTIME_COMPONENTS)


def _add_json(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--json", action="store_true", help="输出机器可读 JSON")


def _add_run(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--run", dest="run_id", help="显式 run ID")


def _add_detach(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--detach", action="store_true", help="启动后立即脱离观察")


def _add_confirm(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--confirm", action="store_true", help="显式批准不可变科学操作")


def _add_prediction_backend(
    parser: argparse.ArgumentParser,
    option: str = "--prediction-backend",
    *,
    required: bool,
) -> None:
    parser.add_argument(
        option,
        choices=("protenix", "afo", "protenix-v2", "openfold3-af3-jax"),
        required=required,
        help="本阶段显式结构预测后端；不会成为项目默认值",
    )


def _prediction_backend(value: str | None) -> str | None:
    if value is None:
        return None
    return {
        "protenix": "protenix-v2",
        "afo": "openfold3-af3-jax",
    }.get(value, value)


def _gpcr_report_base(project: Path, analysis_root: Path) -> Path:
    return (
        project.expanduser().resolve(strict=True)
        / "gpcr-site"
        / "report-rebuilds"
        / analysis_root.name
    )


def _resolved_gpcr_report(project: Path, analysis_root: Path) -> Path:
    rebuilt = _gpcr_report_base(project, analysis_root)
    if (rebuilt / "LATEST").is_file():
        return resolve_latest_gpcr_review_report(rebuilt)
    return resolve_latest_gpcr_review_report(analysis_root / "review")


def _add_project_source(parser: argparse.ArgumentParser) -> None:
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--target", type=Path, help="PSE、本地结构、FASTA 或裸序列")
    source.add_argument("--target-bundle", type=Path)
    source.add_argument("--pdb-id")
    source.add_argument("--uniprot")
    source.add_argument("--uniprot-query")
    parser.add_argument("--source-run-root", type=Path)
    parser.add_argument("--chain")
    parser.add_argument("--chain-namespace", choices=("auth", "label"), default="auth")
    parser.add_argument("--identity-uniprot")
    parser.add_argument("--taxon-id", type=int)
    parser.add_argument("--project-id")
    parser.add_argument("--target-id")
    parser.add_argument("--scope-range", help="例如 25:646")
    parser.add_argument("--scope-feature-type", choices=("Domain", "Chain", "Topological domain"))
    parser.add_argument("--scope-feature-name")
    parser.add_argument("--precomputed-msa", type=Path)
    parser.add_argument(
        "--msa-cache-mode", choices=("online", "prefer-cache", "offline"), default="online"
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="easydesign",
        description="EasyDesign Local：Codex 主导、研究者批准、manifest 可审计的本地研究工作台",
    )
    parser.add_argument("--version", action="version", version=easydesign.__version__)
    parser.add_argument("--debug", action="store_true", help="失败时显示 traceback")
    commands = parser.add_subparsers(dest="command", required=True)

    runtime = commands.add_parser("runtime", help="安装或验证当前 clone 的科学环境/模型")
    runtime_commands = runtime.add_subparsers(dest="runtime_command", required=True)
    runtime_plan = runtime_commands.add_parser(
        "plan", help="只读规划一个或全部本地科学组件及其资产"
    )
    runtime_plan.add_argument("component", choices=(*RUNTIME_PLAN_COMPONENTS, "afo"))
    _add_json(runtime_plan)
    runtime_install = runtime_commands.add_parser(
        "install", help="安装 Miniforge、锁定科学组件或离线 OpenFold3 bundle"
    )
    runtime_install.add_argument(
        "component",
        choices=("miniforge", *RUNTIME_PLAN_COMPONENTS, "afo", "openfold3"),
    )
    runtime_install.add_argument("--bundle", type=Path)
    runtime_install.add_argument("--release")
    runtime_install.add_argument("--detach", action="store_true")
    runtime_install.add_argument(
        "--accept-license",
        action="append",
        default=[],
        metavar="ASSET_ID",
        help="确认一个运行资产许可；可重复提供",
    )
    runtime_install.add_argument("--conda", type=Path, help="显式 Conda executable")
    runtime_install.add_argument(
        "--source",
        choices=SOURCE_POLICIES,
        default="auto",
        help="下载来源策略：自动择优、严格官方或国内优先并回退官方",
    )
    runtime_install.add_argument(
        "--pip-index-url",
        default=None,
        help="仅用于本次安装子进程的 HTTPS Python package index",
    )
    _add_json(runtime_install)
    runtime_activate = runtime_commands.add_parser(
        "activate", help="显式激活一个已安装的 AFO release"
    )
    runtime_activate.add_argument("component", choices=("afo",))
    runtime_activate.add_argument("--release", required=True)
    _add_confirm(runtime_activate)
    _add_json(runtime_activate)
    runtime_list = runtime_commands.add_parser(
        "list", help="列出 AFO candidate/stable、已安装与 active release"
    )
    runtime_list.add_argument("component", choices=("afo",))
    _add_json(runtime_list)
    runtime_jobs = runtime_commands.add_parser("jobs", help="读取持久 runtime 安装任务")
    runtime_jobs.add_argument("--job-id")
    runtime_jobs.add_argument(
        "--watch",
        action="store_true",
        help="持续刷新当前步骤、进度、下载速度和 ETA；Ctrl-C 仅停止观察",
    )
    runtime_jobs.add_argument(
        "--interval",
        type=float,
        default=1.0,
        help="观察刷新间隔秒数（默认 1.0）",
    )
    _add_json(runtime_jobs)
    runtime_status_parser = runtime_commands.add_parser(
        "status", help="验证当前 clone 的本地 component"
    )
    _add_json(runtime_status_parser)
    runtime_compare = runtime_commands.add_parser(
        "compare", help="生成不可变 OpenFold3/Protenix 灰度比较报告"
    )
    runtime_compare.add_argument("component", choices=("afo", "openfold3"))
    runtime_compare.add_argument("--panel", required=True, type=Path)
    runtime_compare.add_argument("--evidence", required=True, type=Path)
    _add_json(runtime_compare)
    runtime_approve = runtime_commands.add_parser(
        "approve", help="记录研究者灰度审核；不会自动切换默认后端"
    )
    runtime_approve.add_argument("component", choices=("afo", "openfold3"))
    runtime_approve.add_argument("--report", required=True, type=Path)
    runtime_approve.add_argument("--reviewer", required=True)
    runtime_approve.add_argument(
        "--decision",
        required=True,
        choices=("approve-stable-promotion", "reject-stable-promotion"),
    )
    runtime_approve.add_argument("--notes", default="")
    _add_confirm(runtime_approve)
    _add_json(runtime_approve)

    doctor = commands.add_parser("doctor", help="检查本地 runtime/backend")
    doctor.add_argument("--full", action="store_true")
    _add_json(doctor)

    project = commands.add_parser("project", help="创建项目或恢复唯一研究状态")
    project_commands = project.add_subparsers(dest="project_command", required=True)
    project_init = project_commands.add_parser("init", help="创建 Agent-native 项目")
    project_init.add_argument("project", type=Path)
    _add_project_source(project_init)
    _add_json(project_init)
    project_status_parser = project_commands.add_parser(
        "status", help="读取 target/site、strategy、pilot、production 和待批准事项"
    )
    project_status_parser.add_argument("project", type=Path)
    _add_json(project_status_parser)

    target = commands.add_parser("target", help="准备与批准靶点身份/结构")
    target_commands = target.add_subparsers(dest="target_command", required=True)
    target_prepare_parser = target_commands.add_parser("prepare")
    target_prepare_parser.add_argument("project", type=Path)
    _add_prediction_backend(target_prepare_parser, required=False)
    target_msa_source = target_prepare_parser.add_mutually_exclusive_group()
    target_msa_source.add_argument(
        "--prediction-config",
        type=Path,
        help="Stage 1 显式 MSA/template 配置片段；backend 必须与命令一致",
    )
    target_msa_source.add_argument(
        "--msa-library",
        help="按 canonical sequence SHA-256 从当前 clone 的版本化 MSA library 解析",
    )
    target_msa_source.add_argument(
        "--msa-a3m",
        type=Path,
        help="显式提供单条 A3M；必须与 target canonical sequence 完全一致",
    )
    _add_detach(target_prepare_parser)
    _add_json(target_prepare_parser)
    target_approve_parser = target_commands.add_parser("approve")
    target_approve_parser.add_argument("project", type=Path)
    target_approve_parser.add_argument("--input", type=Path, required=True)
    _add_detach(target_approve_parser)
    _add_json(target_approve_parser)

    site = commands.add_parser("site", help="提出、扫描和批准 binding site")
    site_commands = site.add_subparsers(dest="site_command", required=True)
    site_propose_parser = site_commands.add_parser("propose")
    site_propose_parser.add_argument("project", type=Path)
    site_source = site_propose_parser.add_mutually_exclusive_group(required=True)
    site_source.add_argument("--from-pse-colors", action="store_true")
    site_source.add_argument("--input", type=Path)
    _add_detach(site_propose_parser)
    _add_json(site_propose_parser)
    site_scan_parser = site_commands.add_parser("scan")
    site_scan_parser.add_argument("project", type=Path)
    site_scan_parser.add_argument("--method", choices=("sasa", "scannet", "both"), required=True)
    site_scan_parser.add_argument("--provider", choices=("auto", "gpcr", "generic"), default="auto")
    site_scan_parser.add_argument("--context", type=Path)
    site_scan_parser.add_argument("--offline", action="store_true")
    _add_detach(site_scan_parser)
    _add_json(site_scan_parser)
    site_approve_parser = site_commands.add_parser("approve")
    site_approve_parser.add_argument("project", type=Path)
    site_approve_parser.add_argument("--input", type=Path, required=True)
    _add_confirm(site_approve_parser)
    _add_json(site_approve_parser)

    strategy = commands.add_parser("strategy", help="起草、校验和冻结实验策略")
    strategy_commands = strategy.add_subparsers(dest="strategy_command", required=True)
    strategy_draft_parser = strategy_commands.add_parser("draft")
    strategy_draft_parser.add_argument("project", type=Path)
    strategy_origin = strategy_draft_parser.add_mutually_exclusive_group()
    strategy_origin.add_argument("--from", dest="source_revision")
    strategy_origin.add_argument("--from-pilot")
    _add_json(strategy_draft_parser)
    strategy_validate_parser = strategy_commands.add_parser("validate")
    strategy_validate_parser.add_argument("project", type=Path)
    strategy_validate_parser.add_argument("--config", type=Path, required=True)
    _add_json(strategy_validate_parser)
    strategy_freeze_parser = strategy_commands.add_parser("freeze")
    strategy_freeze_parser.add_argument("project", type=Path)
    strategy_freeze_parser.add_argument("--config", type=Path, required=True)
    strategy_freeze_parser.add_argument("--plan-sha")
    _add_confirm(strategy_freeze_parser)
    _add_json(strategy_freeze_parser)

    pilot = commands.add_parser("pilot", help="运行、诊断和人工 promotion 小批量实验")
    pilot_commands = pilot.add_subparsers(dest="pilot_command", required=True)
    for name in ("plan", "run"):
        sub = pilot_commands.add_parser(name)
        sub.add_argument("project", type=Path)
        sub.add_argument("--strategy", required=True)
        _add_prediction_backend(sub, required=True)
        if name == "run":
            sub.add_argument("--plan-sha")
            _add_confirm(sub)
            _add_detach(sub)
        _add_json(sub)
    pilot_review_parser = pilot_commands.add_parser("review")
    pilot_review_parser.add_argument("project", type=Path)
    pilot_review_parser.add_argument("--run", dest="run_id", required=True)
    _add_json(pilot_review_parser)
    pilot_interpret_parser = pilot_commands.add_parser("interpret")
    pilot_interpret_parser.add_argument("project", type=Path)
    pilot_interpret_parser.add_argument("--run", dest="run_id", required=True)
    pilot_interpret_parser.add_argument("--input", type=Path, required=True)
    _add_json(pilot_interpret_parser)
    pilot_promote_parser = pilot_commands.add_parser("promote")
    pilot_promote_parser.add_argument("project", type=Path)
    pilot_promote_parser.add_argument("--run", dest="run_id", required=True)
    pilot_promote_parser.add_argument(
        "--strategy", required=True, help="逗号分隔的 StrategyBundle ID"
    )
    pilot_promote_parser.add_argument("--plan-sha")
    _add_confirm(pilot_promote_parser)
    _add_json(pilot_promote_parser)

    scale = commands.add_parser("scale", help="计划和启动规模化生产")
    scale_commands = scale.add_subparsers(dest="scale_command", required=True)
    for name in ("plan", "run"):
        sub = scale_commands.add_parser(name)
        sub.add_argument("project", type=Path)
        sub.add_argument("--selection", required=True)
        sub.add_argument("--count", type=int, default=50_000)
        if name == "run":
            sub.add_argument("--plan-sha")
            _add_confirm(sub)
            _add_detach(sub)
        _add_json(sub)

    select = commands.add_parser("select", help="计划和执行最终候选选择")
    select_commands = select.add_subparsers(dest="select_command", required=True)
    for name in ("plan", "run"):
        sub = select_commands.add_parser(name)
        sub.add_argument("project", type=Path)
        sub.add_argument("--run", dest="run_id", required=True)
        sub.add_argument("--top", type=int, default=200)
        _add_prediction_backend(sub, "--de-novo-backend", required=True)
        _add_prediction_backend(sub, "--target-conditioned-backend", required=True)
        if name == "run":
            sub.add_argument("--plan-sha")
            _add_confirm(sub)
            _add_detach(sub)
        _add_json(sub)

    job = commands.add_parser("job", help="观察、恢复或安全 drain 本地任务")
    job_commands = job.add_subparsers(dest="job_command", required=True)
    for name in ("status", "watch", "resume", "drain"):
        sub = job_commands.add_parser(name)
        sub.add_argument("project", type=Path)
        if name != "drain":
            _add_run(sub)
        else:
            sub.add_argument("--job", dest="job_id")
        if name == "resume":
            _add_detach(sub)
        _add_json(sub)

    view = commands.add_parser("view", help="启动只读 evidence viewer")
    view.add_argument("project", type=Path)
    _add_run(view)
    view.add_argument("--port", type=int, default=8000)
    view.add_argument(
        "--report",
        choices=("auto", "target", "gpcr", "stage05", "stage07"),
        default="auto",
    )
    _add_json(view)

    report = commands.add_parser("report", help="重建或导出不可变 review dashboard")
    report_commands = report.add_subparsers(dest="report_command", required=True)
    report_build = report_commands.add_parser("build", help="为旧 run 或 reporting failure 重建")
    report_build.add_argument("project", type=Path)
    _add_run(report_build)
    report_build.add_argument("--report", choices=("gpcr", "stage05", "stage07"), required=True)
    report_build.add_argument(
        "--presentation",
        type=Path,
        help="可选 YAML/JSON，仅允许标题、中文标签、指标顺序和默认图轴",
    )
    _add_json(report_build)
    report_export = report_commands.add_parser("export", help="生成包含全部结构的便携报告")
    report_export.add_argument("project", type=Path)
    _add_run(report_export)
    report_export.add_argument("--report", choices=("gpcr", "stage05", "stage07"), required=True)
    report_export.add_argument("--output", type=Path, required=True)
    _add_json(report_export)

    gpcr = commands.add_parser("gpcr", help="独立 GPCR 分析、批量只读报告和 bundle 校验")
    gpcr_commands = gpcr.add_subparsers(dest="gpcr_command", required=True)
    gpcr_analyze = gpcr_commands.add_parser("analyze")
    gpcr_analyze.add_argument("--structure", type=Path, required=True)
    gpcr_analyze.add_argument("--output-dir", type=Path, required=True)
    gpcr_analyze.add_argument("--mode", choices=("both", "inhibit", "activate"), default="both")
    identity = gpcr_analyze.add_mutually_exclusive_group(required=True)
    identity.add_argument("--gpcr-entry")
    identity.add_argument("--accession")
    gpcr_analyze.add_argument("--receptor-chain", required=True)
    gpcr_analyze.add_argument("--context", type=Path)
    gpcr_analyze.add_argument("--membrane-orientation", type=Path)
    gpcr_analyze.add_argument("--state")
    gpcr_analyze.add_argument("--offline", action="store_true")
    _add_json(gpcr_analyze)
    gpcr_batch = gpcr_commands.add_parser("batch-review")
    gpcr_batch.add_argument("--input", type=Path, required=True)
    gpcr_batch.add_argument("--output-dir", type=Path, required=True)
    gpcr_batch.add_argument("--mode", choices=("both", "inhibit", "activate"), default="both")
    gpcr_batch.add_argument("--offline", action="store_true")
    _add_json(gpcr_batch)
    gpcr_validate = gpcr_commands.add_parser("validate")
    gpcr_validate.add_argument("--bundle", type=Path, required=True)
    _add_json(gpcr_validate)

    return parser


def _scope_range(value: str | None) -> tuple[int, int] | None:
    if value is None:
        return None
    try:
        start, end = (int(item) for item in value.split(":", maxsplit=1))
    except (TypeError, ValueError) as error:
        raise ValueError("--scope-range 必须是 START:END") from error
    return start, end


def _json(value: BaseModel | dict[str, Any]) -> str:
    payload = value.model_dump(mode="json") if isinstance(value, BaseModel) else value
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)


def _print_runtime_plan(payload: dict[str, Any]) -> None:
    print(f"组件: {payload['component']}")
    print(f"工作区: {payload['workspace']}")
    for environment in payload["environments"]:
        print(
            f"环境: {environment['environment_id']} -> {environment['target']} "
            f"(lock {str(environment['lock_sha256'])[:12]})"
        )
    for asset in payload["assets"]:
        gate = "需要许可确认" if asset["license_confirmation_required"] else "无需确认"
        print(f"资产: {asset['asset_id']} ({asset['license']}; {gate})")
    disk = payload["disk"]
    print(
        "磁盘: "
        f"可用 {disk['free_bytes']} bytes; "
        f"增量峰值 {disk['incremental_peak_bytes']} bytes; "
        f"保留 {disk['reserve_bytes']} bytes"
    )
    print("结论: " + ("空间满足要求" if disk["sufficient"] else "空间不足"))


def _confirmed_runtime_licenses(
    payload: dict[str, Any],
    *,
    accepted: set[str],
    allow_prompt: bool,
) -> set[str]:
    pending = [
        asset
        for asset in payload["assets"]
        if asset["license_confirmation_required"] and asset["asset_id"] not in accepted
    ]
    if not pending or not allow_prompt:
        return accepted
    print("以下资产需要在下载前逐项确认许可：")
    for asset in pending:
        answer = input(
            f"- {asset['asset_id']} ({asset['license']})，确认下载并用于本机运行？[y/N] "
        )
        if answer.strip().lower() in {"y", "yes"}:
            accepted.add(str(asset["asset_id"]))
    return accepted


def _runtime_status_payload(context: WorkspaceContext) -> dict[str, Any]:
    components = runtime_status().model_dump(mode="json")
    miniforge = miniforge_status(context)
    components["miniforge"] = None if miniforge is None else miniforge.model_dump(mode="json")
    component_assets = {
        asset_id
        for component in LOCAL_RUNTIME_COMPONENTS
        for asset_id in SETUP_COMPONENT_ASSETS[component]
    }
    components["local_environments"] = [
        item
        for item in environment_status(context)["environments"]
        if item["environment_id"] in LOCAL_RUNTIME_COMPONENTS
    ]
    components["local_assets"] = [
        item for item in asset_status(context)["assets"] if item["asset_id"] in component_assets
    ]
    return components


def _print_runtime_status(payload: dict[str, Any]) -> None:
    print("Runtime scope: current clone")
    miniforge = payload["miniforge"]
    print(
        "Miniforge: "
        + (str(miniforge["conda_version"]) if miniforge is not None else "not-installed")
    )
    openfold3 = payload["openfold3"]
    print(
        "OpenFold3: "
        + (str(openfold3["converted_weight_sha256"]) if openfold3 is not None else "not-installed")
    )
    for environment in payload["local_environments"]:
        print(f"Local environment {environment['environment_id']}: {environment['status']}")
    for asset in payload["local_assets"]:
        print(f"Local asset {asset['asset_id']}: {asset['status']}")


def _human_bytes(value: float) -> str:
    units = ("B", "KiB", "MiB", "GiB", "TiB")
    amount = value
    for unit in units:
        if abs(amount) < 1024 or unit == units[-1]:
            return f"{amount:.1f} {unit}" if unit != "B" else f"{amount:.0f} B"
        amount /= 1024
    raise AssertionError("unreachable")


def _human_duration(seconds: float) -> str:
    rounded = max(int(seconds), 0)
    minutes, second = divmod(rounded, 60)
    hours, minute = divmod(minutes, 60)
    if hours:
        return f"{hours}h{minute:02d}m"
    if minutes:
        return f"{minutes}m{second:02d}s"
    return f"{second}s"


def _format_setup_job_progress(job: SetupJobProjection) -> str:
    progress = job.progress
    if progress is None:
        return f"{job.job_id}: {job.status}; 等待 worker 发布进度"
    total = max(progress.total_steps, 1)
    fraction = (progress.completed_steps + progress.current_step_fraction) / total
    if job.status == "succeeded":
        fraction = 1.0
    fraction = max(0.0, min(fraction, 1.0))
    width = 24
    filled = min(int(fraction * width), width)
    bar = "█" * filled + "░" * (width - filled)
    details = [
        f"[{bar}] {fraction * 100:5.1f}%",
        job.status,
        progress.phase,
        progress.current_item or job.component or "runtime",
        progress.message,
    ]
    if progress.bytes_completed is not None:
        downloaded = _human_bytes(float(progress.bytes_completed))
        if progress.bytes_total is not None:
            downloaded += f"/{_human_bytes(float(progress.bytes_total))}"
        details.append(downloaded)
    if progress.bytes_per_second is not None and progress.bytes_per_second > 0:
        details.append(f"{_human_bytes(progress.bytes_per_second)}/s")
    if progress.eta_seconds is not None:
        details.append(f"ETA {_human_duration(progress.eta_seconds)}")
    return " | ".join(details)


def _print_setup_job(job: SetupJobProjection) -> None:
    print(_format_setup_job_progress(job))
    print(f"  stdout: {job.stdout_relative_path}")
    print(f"  stderr: {job.stderr_relative_path}")
    if job.error:
        print(f"  error: {job.error}")
    if job.afo is not None:
        print(f"  AFO stable: {job.afo.component.release_id} ({job.afo.status})")


def _watch_setup_job(
    context: WorkspaceContext,
    job_id: str,
    *,
    interval: float,
) -> SetupJobProjection:
    if interval <= 0:
        raise ConfigurationError("--interval 必须大于 0")
    interactive = sys.stdout.isatty()
    last_line: str | None = None
    try:
        while True:
            job = read_setup_job(context, job_id)
            line = _format_setup_job_progress(job)
            if interactive:
                sys.stdout.write("\r\x1b[2K" + line)
                sys.stdout.flush()
            elif line != last_line:
                print(line, flush=True)
            last_line = line
            if job.status != "running":
                if interactive:
                    print()
                _print_setup_job(job)
                return job
            time.sleep(interval)
    except KeyboardInterrupt:
        if interactive:
            print()
        print("已停止观察；后台安装任务仍在运行。")
        return read_setup_job(context, job_id)


def _print_result(result: CommandResult, *, as_json: bool) -> None:
    if as_json:
        print(_json(result))
        return
    print(f"状态: {result.status}")
    print(f"阶段: {result.phase}")
    print(f"项目: {result.project_id}")
    if result.run_id:
        print(f"Run: {result.run_id}")
    if result.job_id:
        print(f"Job: {result.job_id}")
    if result.manifest:
        print(f"Manifest: {result.manifest}")
    if result.artifacts:
        print("产物:")
        for path in result.artifacts:
            print(f"  - {path}")
    if result.evidence:
        print("证据:")
        for item in result.evidence:
            suffix = f" ({item.path})" if item.path else ""
            print(f"  - {item.kind}: {item.identity}: {item.status}{suffix}")
    if result.next_actions:
        print("下一步:")
        for action in result.next_actions:
            gate = " [需要研究者批准]" if action.approval_required else ""
            print(f"  - {action.description}{gate}\n    {action.command}")
    for warning in result.warnings:
        print(f"警告: {warning}")


def _project_init_values(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "project_root": args.project,
        "target": args.target,
        "target_bundle": args.target_bundle,
        "source_run_root": args.source_run_root,
        "pdb_id": args.pdb_id,
        "uniprot": args.uniprot,
        "uniprot_query": args.uniprot_query,
        "taxon_id": args.taxon_id,
        "chain": args.chain,
        "chain_namespace": args.chain_namespace,
        "identity_uniprot": args.identity_uniprot,
        "project_id": args.project_id,
        "target_id": args.target_id,
        "scope_range": _scope_range(args.scope_range),
        "scope_feature_type": args.scope_feature_type,
        "scope_feature_name": args.scope_feature_name,
        "precomputed_msa": args.precomputed_msa,
        "msa_cache_mode": args.msa_cache_mode,
    }


def _dispatch(args: argparse.Namespace) -> int:
    if args.command == "runtime":
        context = WorkspaceContext.discover()
        if args.runtime_command == "plan":
            if args.component == "afo":
                catalog = load_afo_release_catalog(context)
                payload = {
                    "component": "afo",
                    "default_channel": "stable",
                    "releases": [item.model_dump(mode="json") for item in catalog.releases],
                }
                if args.json:
                    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
                else:
                    print("AFO default channel: stable")
                    for item in catalog.releases:
                        state = "installable" if item.bundle is not None else "pending-assets"
                        print(
                            f"{item.release_id}: {item.channel}; "
                            f"alphafold3-open {item.backend_version}; {state}"
                        )
            else:
                plan = setup_plan(context, component=args.component)
                if args.json:
                    print(_json(plan))
                else:
                    _print_runtime_plan(plan)
        elif args.runtime_command == "install":
            if args.component == "miniforge":
                if (
                    args.bundle is not None
                    or args.release is not None
                    or args.detach
                    or args.accept_license
                    or args.conda is not None
                    or args.pip_index_url is not None
                ):
                    raise ConfigurationError(
                        "Miniforge 安装不接受 bundle、detach、许可、Conda 或 pip index 参数"
                    )
                if not args.json:
                    print("正在下载、校验并安装工作区专用 Miniforge……", flush=True)
                miniforge_result = install_miniforge(
                    context,
                    show_progress=not args.json,
                    source_policy=args.source,
                )
                print(
                    _json(miniforge_result)
                    if args.json
                    else (
                        f"Miniforge: {miniforge_result.status}\n"
                        f"Release: {miniforge_result.receipt.release}\n"
                        f"Source: {miniforge_result.receipt.transport_source_id}\n"
                        f"Conda: {miniforge_result.receipt.conda_executable}\n"
                        f"Version: {miniforge_result.receipt.conda_version}\n"
                        f"Receipt: {miniforge_result.receipt_path}"
                    )
                )
            elif args.component in {"afo", "openfold3"}:
                if args.component == "openfold3" and args.release is not None:
                    raise ConfigurationError("兼容 openfold3 入口不接受 --release")
                if args.bundle is None:
                    if args.component == "openfold3":
                        raise ConfigurationError("兼容 OpenFold3 入口必须提供 --bundle")
                    release = load_afo_release_catalog(context).resolve(
                        release_id=args.release,
                        channel="stable",
                    )
                    selected_bundle = materialize_afo_bundle(
                        release,
                        source_policy=args.source,
                        context=context,
                    )
                    activate = args.release is None
                else:
                    if args.release is not None:
                        raise ConfigurationError("--bundle 与 --release 不能同时使用")
                    selected_bundle = args.bundle
                    activate = True
                if (
                    args.detach
                    or args.accept_license
                    or args.conda is not None
                    or args.pip_index_url is not None
                    or (args.bundle is not None and args.source != "auto")
                ):
                    raise ConfigurationError("AFO 不接受 Conda、许可、detach 或 bundle source 参数")
                openfold3_result = install_openfold3_component(
                    selected_bundle,
                    activate=activate,
                )
                print(
                    _json(openfold3_result)
                    if args.json
                    else (
                        f"OpenFold3 component: {openfold3_result.status}\n"
                        f"Release: {openfold3_result.component.release_id}\n"
                        f"Environment: {openfold3_result.component.environment_root}\n"
                        f"Model: {openfold3_result.component.model_root}\n"
                        f"Profile: {openfold3_result.profile}"
                    )
                )
            else:
                if args.bundle is not None or args.release is not None:
                    raise ConfigurationError("--bundle/--release 只用于 AFO")
                plan = setup_plan(context, component=args.component)
                accepted = _confirmed_runtime_licenses(
                    plan,
                    accepted=set(args.accept_license),
                    allow_prompt=not args.json and sys.stdin.isatty(),
                )
                if args.detach:
                    job = launch_setup_job(
                        context,
                        component=args.component,
                        accepted_license_ids=accepted,
                        conda_executable=args.conda,
                        pip_index_url=args.pip_index_url,
                        source_policy=args.source,
                    )
                    print(
                        _json(job)
                        if args.json
                        else (
                            f"Runtime job: {job.job_id}\n"
                            f"Status: {job.status}\n"
                            "查看实时进度：\n"
                            f"  easydesign runtime jobs --job-id {job.job_id} --watch"
                        )
                    )
                else:
                    setup_summary = setup_workspace(
                        context,
                        component=args.component,
                        accepted_license_ids=accepted,
                        conda_executable=args.conda,
                        pip_index_url=args.pip_index_url,
                        source_policy=args.source,
                    )
                    afo_result = (
                        install_stable_afo_if_available(
                            source_policy=args.source,
                            context=context,
                        )
                        if setup_summary.ok and args.component == "all"
                        else None
                    )
                    if args.json:
                        setup_payload: dict[str, Any] = setup_summary.model_dump(mode="json")
                        setup_payload["afo"] = (
                            None if afo_result is None else afo_result.model_dump(mode="json")
                        )
                        print(_json(setup_payload))
                    else:
                        summary_status = "succeeded" if setup_summary.ok else "incomplete"
                        print(f"组件: {setup_summary.component}\n状态: {summary_status}")
                        for environment in setup_summary.environments:
                            print(f"Environment {environment.environment_id}: {environment.status}")
                        for asset in setup_summary.assets:
                            print(f"Asset {asset.asset_id}: {asset.status}")
                        if afo_result is not None:
                            print(
                                "AFO stable: "
                                f"{afo_result.component.release_id} ({afo_result.status})"
                            )
                    return 0 if setup_summary.ok else 3
        elif args.runtime_command == "activate":
            if not args.confirm:
                raise ConfigurationError("激活 AFO release 需要 --confirm")
            profile = activate_openfold3_release(args.release, context=context)
            activation_payload = {"release_id": args.release, "profile": str(profile)}
            print(
                json.dumps(activation_payload, ensure_ascii=False, indent=2, sort_keys=True)
                if args.json
                else f"AFO active release: {args.release}\nProfile: {profile}"
            )
        elif args.runtime_command == "list":
            catalog = load_afo_release_catalog(context)
            installed = list_openfold3_components(context)
            active = runtime_status().openfold3
            list_payload: dict[str, Any] = {
                "catalog": [item.model_dump(mode="json") for item in catalog.releases],
                "installed": [item.model_dump(mode="json") for item in installed],
                "active_release_id": None if active is None else active.release_id,
            }
            if args.json:
                print(json.dumps(list_payload, ensure_ascii=False, indent=2, sort_keys=True))
            else:
                for item in catalog.releases:
                    installed_mark = any(
                        receipt.release_id == item.release_id for receipt in installed
                    )
                    active_mark = active is not None and active.release_id == item.release_id
                    print(
                        f"{item.release_id}: channel={item.channel}; "
                        f"installed={installed_mark}; active={active_mark}"
                    )
        elif args.runtime_command == "jobs":
            if args.watch and args.job_id is None:
                raise ConfigurationError("--watch 必须同时指定 --job-id")
            if args.watch and args.json:
                raise ConfigurationError("--watch 与 --json 不能同时使用")
            if args.watch:
                _watch_setup_job(context, args.job_id, interval=args.interval)
                return 0
            jobs = (
                (read_setup_job(context, args.job_id),)
                if args.job_id is not None
                else list_setup_jobs(context)
            )
            if args.json:
                print(
                    json.dumps(
                        [job.model_dump(mode="json") for job in jobs],
                        ensure_ascii=False,
                        indent=2,
                        sort_keys=True,
                    )
                )
            elif not jobs:
                print("当前工作区还没有 runtime 安装任务。")
            else:
                for job in jobs:
                    _print_setup_job(job)
        elif args.runtime_command == "status":
            runtime_payload = _runtime_status_payload(context)
            if args.json:
                print(_json(runtime_payload))
            else:
                _print_runtime_status(runtime_payload)
        elif args.runtime_command == "compare":
            validation_report_path = generate_openfold3_validation_report(
                panel_path=args.panel,
                evidence_path=args.evidence,
            )
            print(
                json.dumps({"report": str(validation_report_path)}, ensure_ascii=False)
                if args.json
                else f"OpenFold3 validation report: {validation_report_path}"
            )
        else:
            approval = approve_openfold3_validation_report(
                report_path=args.report,
                reviewer=args.reviewer,
                decision=cast(
                    Literal[
                        "approve-stable-promotion",
                        "reject-stable-promotion",
                    ],
                    args.decision,
                ),
                notes=args.notes,
                confirm=args.confirm,
            )
            print(
                json.dumps({"approval": str(approval)}, ensure_ascii=False)
                if args.json
                else (
                    f"OpenFold3 approval receipt: {approval}\n"
                    "默认后端尚未改变；切换需要单独的 science commit。"
                )
            )
        return 0
    if args.command == "doctor":
        doctor_report = diagnose_runtime(full=args.full)
        if args.json:
            print(_json(doctor_report))
        else:
            for check in doctor_report.checks:
                print(f"{check.status}: {check.name}: {check.message}")
        return 0 if doctor_report.ok else 2
    if args.command == "report":
        if args.report == "gpcr":
            analysis_root = resolve_latest_gpcr_analysis(args.project)
            if args.report_command == "build":
                gpcr_report_outcome = generate_gpcr_review_report(
                    analysis_root / "gpcr-hotspot-analysis.json",
                    _gpcr_report_base(args.project, analysis_root),
                )
                report_payload: dict[str, Any] = {
                    "status": "succeeded",
                    "manifest": str(gpcr_report_outcome.manifest_path),
                    "entrypoint": str(gpcr_report_outcome.index_path),
                }
            else:
                report_root = _resolved_gpcr_report(args.project, analysis_root)
                exported = export_gpcr_review_report(report_root, args.output)
                report_payload = {"status": "succeeded", "output": str(exported)}
            print(
                json.dumps(report_payload, ensure_ascii=False, indent=2, sort_keys=True)
                if args.json
                else "\n".join(f"{key}: {value}" for key, value in report_payload.items())
            )
            return 0
        summary = resolve_project_run(args.project, run_id=args.run_id, required=True)
        assert summary is not None
        report_kind = cast(Literal["stage05", "stage07"], args.report)
        if args.report_command == "build":
            presentation = (
                None
                if args.presentation is None
                else ReviewDashboardPresentationOverride.model_validate(
                    yaml.safe_load(args.presentation.read_text(encoding="utf-8"))
                )
            )
            dashboard_outcome = generate_review_dashboard(
                summary.path,
                report_kind=report_kind,
                presentation=presentation,
            )
            dashboard_payload = dashboard_outcome.model_dump(mode="json")
            print(
                json.dumps(dashboard_payload, ensure_ascii=False, indent=2, sort_keys=True)
                if args.json
                else (
                    f"Dashboard status: {dashboard_outcome.status}\n"
                    f"Manifest: {dashboard_outcome.manifest_path}\n"
                    + (
                        f"Entrypoint: {dashboard_outcome.entrypoint}"
                        if dashboard_outcome.entrypoint is not None
                        else f"Error: {dashboard_outcome.error}"
                    )
                )
            )
            return 0 if dashboard_outcome.entrypoint is not None else 2
        report_root = resolve_latest_review_dashboard(summary.path, report_kind)
        exported = export_review_dashboard(
            report_root,
            run_root=summary.path,
            output=args.output,
        )
        dashboard_payload = {"status": "succeeded", "output": str(exported)}
        print(
            json.dumps(dashboard_payload, ensure_ascii=False, indent=2, sort_keys=True)
            if args.json
            else f"Portable dashboard: {exported}"
        )
        return 0

    if args.command == "gpcr":
        if args.gpcr_command == "analyze":
            gpcr_analysis_outcome = publish_gpcr_analysis(
                GpcrSiteRequest(
                    evidence_dir=args.output_dir / ".unused-evidence",
                    structure=args.structure,
                    mode=args.mode,
                    gpcr_entry=args.gpcr_entry,
                    accession=args.accession,
                    receptor_chain=args.receptor_chain,
                    selection=args.context,
                    membrane_orientation=args.membrane_orientation,
                    state=args.state,
                    cache_mode="offline" if args.offline else "online",
                ),
                args.output_dir,
            )
            gpcr_payload: dict[str, Any] = {
                "status": "awaiting-human-review",
                "manifest": str(gpcr_analysis_outcome.manifest_path),
                "analysis": str(gpcr_analysis_outcome.analysis_path),
                "context": str(gpcr_analysis_outcome.context_path),
                "selection": str(gpcr_analysis_outcome.selection_path),
                "report": str(gpcr_analysis_outcome.report_root / "index.html"),
            }
        elif args.gpcr_command == "batch-review":
            gpcr_batch_outcome = generate_gpcr_review_report(
                args.input,
                args.output_dir,
                mode=args.mode,
            )
            gpcr_payload = {
                "status": "succeeded",
                "manifest": str(gpcr_batch_outcome.manifest_path),
                "entrypoint": str(gpcr_batch_outcome.index_path),
                "structure_count": gpcr_batch_outcome.structure_count,
            }
        else:
            supplied = args.bundle.expanduser().resolve(strict=True)
            if (
                (supplied / "review-manifest.json").is_file()
                or (supplied / "LATEST").is_file()
                and any(supplied.glob("report-*"))
            ):
                manifest = validate_gpcr_review_report(supplied)
            else:
                manifest = validate_gpcr_analysis_bundle(supplied)
            gpcr_payload = {
                "status": "valid",
                "schema_version": manifest.get("schema_version"),
                "bundle": str(supplied),
            }
        print(
            json.dumps(gpcr_payload, ensure_ascii=False, indent=2, sort_keys=True)
            if args.json
            else "\n".join(f"{key}: {value}" for key, value in gpcr_payload.items())
        )
        return 0

    result: CommandResult
    if args.command == "project":
        result = (
            initialize_research_project(**_project_init_values(args))
            if args.project_command == "init"
            else project_status(args.project)
        )
    elif args.command == "target":
        result = (
            target_prepare(
                args.project,
                prediction_backend=cast(
                    Any,
                    _prediction_backend(args.prediction_backend),
                ),
                prediction_config_path=args.prediction_config,
                msa_library=args.msa_library,
                msa_a3m=args.msa_a3m,
                detach=args.detach,
            )
            if args.target_command == "prepare"
            else target_approve(args.project, input_path=args.input, detach=args.detach)
        )
    elif args.command == "site":
        if args.site_command == "propose":
            result = site_propose(
                args.project,
                input_path=args.input,
                from_pse_colors=args.from_pse_colors,
                detach=args.detach,
            )
        elif args.site_command == "scan":
            result = site_scan(
                args.project,
                method=args.method,
                provider=args.provider,
                context_path=args.context,
                offline=args.offline,
                detach=args.detach,
            )
        else:
            result = site_approve(args.project, input_path=args.input, confirm=args.confirm)
    elif args.command == "strategy":
        if args.strategy_command == "draft":
            result = strategy_draft(
                args.project, source=args.source_revision, from_pilot=args.from_pilot
            )
        elif args.strategy_command == "validate":
            result = strategy_validate(args.project, config_path=args.config)
        else:
            result = strategy_freeze(
                args.project,
                config_path=args.config,
                confirm=args.confirm,
                plan_sha=args.plan_sha,
            )
    elif args.command == "pilot":
        if args.pilot_command == "plan":
            result = pilot_plan(
                args.project,
                strategy_revision=args.strategy,
                prediction_backend=cast(Any, _prediction_backend(args.prediction_backend)),
            )
        elif args.pilot_command == "run":
            result = pilot_run(
                args.project,
                strategy_revision=args.strategy,
                prediction_backend=cast(Any, _prediction_backend(args.prediction_backend)),
                confirm=args.confirm,
                detach=args.detach,
                plan_sha=args.plan_sha,
            )
        elif args.pilot_command == "review":
            result = pilot_review(args.project, run_id=args.run_id)
        elif args.pilot_command == "interpret":
            result = pilot_interpret(
                args.project,
                run_id=args.run_id,
                input_path=args.input,
            )
        else:
            result = pilot_promote(
                args.project,
                run_id=args.run_id,
                strategy_ids=tuple(
                    item.strip() for item in args.strategy.split(",") if item.strip()
                ),
                confirm=args.confirm,
                plan_sha=args.plan_sha,
            )
    elif args.command == "scale":
        result = (
            scale_plan(args.project, selection=args.selection, count=args.count)
            if args.scale_command == "plan"
            else scale_run(
                args.project,
                selection=args.selection,
                count=args.count,
                confirm=args.confirm,
                detach=args.detach,
                plan_sha=args.plan_sha,
            )
        )
    elif args.command == "select":
        result = (
            select_plan(
                args.project,
                run_id=args.run_id,
                de_novo_backend=cast(Any, _prediction_backend(args.de_novo_backend)),
                target_conditioned_backend=cast(
                    Any,
                    _prediction_backend(args.target_conditioned_backend),
                ),
                top=args.top,
            )
            if args.select_command == "plan"
            else select_run(
                args.project,
                run_id=args.run_id,
                de_novo_backend=cast(Any, _prediction_backend(args.de_novo_backend)),
                target_conditioned_backend=cast(
                    Any,
                    _prediction_backend(args.target_conditioned_backend),
                ),
                top=args.top,
                confirm=args.confirm,
                detach=args.detach,
                plan_sha=args.plan_sha,
            )
        )
    elif args.command == "job":
        if args.job_command == "status":
            result = job_status(args.project, run_id=args.run_id)
        elif args.job_command == "watch":
            result = job_watch(args.project, run_id=args.run_id)
        elif args.job_command == "resume":
            result = job_resume(args.project, run_id=args.run_id, detach=args.detach)
        else:
            result = job_drain(args.project, job_id=args.job_id)
    elif args.command == "view":
        direct_report = args.project.expanduser().resolve()
        if args.report == "gpcr":
            analysis_root = resolve_latest_gpcr_analysis(args.project)
            report_root = _resolved_gpcr_report(args.project, analysis_root)
            gpcr_server = create_gpcr_review_server(report_root, port=args.port)
            status_result = project_status(args.project)
            result = CommandResult(
                status="serving",
                phase="prepare",
                project_id=status_result.project_id,
                manifest=analysis_root / "analysis-manifest.json",
                next_actions=(),
            )
            _print_result(result, as_json=args.json)
            print(gpcr_server.url)
            try:
                gpcr_server.serve_forever()
            except KeyboardInterrupt:
                pass
            finally:
                gpcr_server.close()
            return 0
        if (direct_report / "report-manifest.json").is_file() and (
            direct_report / "report.json"
        ).is_file():
            portable = load_model(
                direct_report / "report.json",
                ReviewDashboardReport,
            )
            portable_server = create_review_dashboard_server(
                direct_report,
                run_root=direct_report,
                port=args.port,
            )
            result = CommandResult(
                status="serving",
                phase="select" if portable.report_kind == "stage07" else "pilot",
                project_id=portable.project_id,
                run_id=portable.run_id,
                next_actions=(),
            )
            _print_result(result, as_json=args.json)
            print(portable_server.url)
            try:
                portable_server.serve_forever()
            except KeyboardInterrupt:
                pass
            finally:
                portable_server.close()
            return 0
        summary = resolve_project_run(args.project, run_id=args.run_id, required=True)
        assert summary is not None
        internal = completed_steps(summary.path)
        requested_report = args.report
        if requested_report == "auto":
            requested_report = (
                "stage07" if 7 in internal else "stage05" if 5 in internal else "target"
            )
        server: Any
        if requested_report == "target":
            report_root = resolve_target_viewer_argument(summary.path)
            server = create_target_viewer_server(
                report_root,
                port=args.port,
                stage02_overlay=build_stage02_viewer_overlay(summary.path),
                evidence=build_evidence_viewer_payload(summary.path),
            )
        else:
            report_kind = cast(Literal["stage05", "stage07"], requested_report)
            report_root = resolve_latest_review_dashboard(summary.path, report_kind)
            server = create_review_dashboard_server(
                report_root,
                run_root=summary.path,
                port=args.port,
            )
        phase: ResearchPhase = (
            "select"
            if 7 in internal
            else "scale"
            if 6 in internal
            else "pilot"
            if any(step in internal for step in (3, 4, 5))
            else "prepare"
        )
        result = CommandResult(
            status="serving",
            phase=phase,
            project_id=summary.project_id,
            run_id=summary.run_id,
            manifest=summary.latest_manifest,
            next_actions=(),
        )
        _print_result(result, as_json=args.json)
        print(server.url)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            server.close()
        return 0
    else:
        raise RuntimeError(f"未知 command: {args.command}")
    _print_result(result, as_json=args.json)
    return 2 if result.status in {"operational-failed", "scientific-failed"} else 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    try:
        os.environ.update(WorkspaceContext.discover().child_environment())
        return _dispatch(args)
    except (EasyDesignError, OSError, ValueError) as error:
        if getattr(args, "debug", False):
            traceback.print_exc()
        else:
            print(f"ERROR: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
