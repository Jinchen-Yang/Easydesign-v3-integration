"""EasyDesign Local agent-native research command line."""

from __future__ import annotations

import argparse
import json
import os
import sys
import traceback
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Literal, cast

from pydantic import BaseModel

import easydesign
from easydesign.core import EasyDesignError
from easydesign.orchestration.application import diagnose_runtime
from easydesign.orchestration.local_project import completed_steps, resolve_project_run
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
    install_openfold3_component,
    runtime_status,
)
from easydesign.orchestration.runtime_link import link_runtime
from easydesign.reporting import (
    build_evidence_viewer_payload,
    build_stage02_viewer_overlay,
    create_target_viewer_server,
    resolve_target_viewer_argument,
)
from easydesign.workspace_context import WorkspaceContext


def _add_json(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--json", action="store_true", help="输出机器可读 JSON")


def _add_run(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--run", dest="run_id", help="显式 run ID")


def _add_detach(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--detach", action="store_true", help="启动后立即脱离观察")


def _add_confirm(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--confirm", action="store_true", help="显式批准不可变科学操作")


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

    runtime = commands.add_parser("runtime", help="链接或验证本机科学环境/模型")
    runtime_commands = runtime.add_subparsers(dest="runtime_command", required=True)
    runtime_link = runtime_commands.add_parser("link", help="只读复用已安装 runtime")
    runtime_link.add_argument("source", type=Path)
    _add_json(runtime_link)
    runtime_install = runtime_commands.add_parser(
        "install", help="从离线 bundle 安装本地 immutable component"
    )
    runtime_install.add_argument("component", choices=("openfold3",))
    runtime_install.add_argument("--bundle", required=True, type=Path)
    _add_json(runtime_install)
    runtime_status_parser = runtime_commands.add_parser(
        "status", help="验证 shared link 与本地 component"
    )
    _add_json(runtime_status_parser)
    runtime_compare = runtime_commands.add_parser(
        "compare", help="生成不可变 OpenFold3/Protenix 灰度比较报告"
    )
    runtime_compare.add_argument("component", choices=("openfold3",))
    runtime_compare.add_argument("--panel", required=True, type=Path)
    runtime_compare.add_argument("--evidence", required=True, type=Path)
    _add_json(runtime_compare)
    runtime_approve = runtime_commands.add_parser(
        "approve", help="记录研究者灰度审核；不会自动切换默认后端"
    )
    runtime_approve.add_argument("component", choices=("openfold3",))
    runtime_approve.add_argument("--report", required=True, type=Path)
    runtime_approve.add_argument("--reviewer", required=True)
    runtime_approve.add_argument(
        "--decision",
        required=True,
        choices=("approve-default-switch", "reject-default-switch"),
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
    _add_confirm(strategy_freeze_parser)
    _add_json(strategy_freeze_parser)

    pilot = commands.add_parser("pilot", help="运行、诊断和人工 promotion 小批量实验")
    pilot_commands = pilot.add_subparsers(dest="pilot_command", required=True)
    for name in ("plan", "run"):
        sub = pilot_commands.add_parser(name)
        sub.add_argument("project", type=Path)
        sub.add_argument("--strategy", required=True)
        if name == "run":
            _add_confirm(sub)
            _add_detach(sub)
        _add_json(sub)
    pilot_review_parser = pilot_commands.add_parser("review")
    pilot_review_parser.add_argument("project", type=Path)
    pilot_review_parser.add_argument("--run", dest="run_id", required=True)
    _add_json(pilot_review_parser)
    pilot_promote_parser = pilot_commands.add_parser("promote")
    pilot_promote_parser.add_argument("project", type=Path)
    pilot_promote_parser.add_argument("--run", dest="run_id", required=True)
    pilot_promote_parser.add_argument(
        "--strategy", required=True, help="逗号分隔的 StrategyBundle ID"
    )
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
        if name == "run":
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
    _add_json(view)
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
        if args.runtime_command == "link":
            link_result = link_runtime(args.source)
            print(
                _json(link_result)
                if args.json
                else (
                    f"已链接只读 runtime: {link_result.source_runtime}\n"
                    f"Profile: {link_result.profile}\nReceipt: {link_result.receipt}"
                )
            )
        elif args.runtime_command == "install":
            installed = install_openfold3_component(args.bundle)
            print(
                _json(installed)
                if args.json
                else (
                    f"OpenFold3 component: {installed.status}\n"
                    f"Environment: {installed.component.environment_root}\n"
                    f"Model: {installed.component.model_root}\n"
                    f"Profile: {installed.profile}"
                )
            )
        elif args.runtime_command == "status":
            status = runtime_status()
            openfold3_status = (
                status.openfold3.converted_weight_sha256
                if status.openfold3
                else "not-installed"
            )
            print(
                _json(status)
                if args.json
                else (
                    f"Shared runtime: {status.linked_runtime}\n"
                    f"OpenFold3: {openfold3_status}"
                )
            )
        elif args.runtime_command == "compare":
            validation_report_path = generate_openfold3_validation_report(
                panel_path=args.panel,
                evidence_path=args.evidence,
            )
            print(
                json.dumps(
                    {"report": str(validation_report_path)}, ensure_ascii=False
                )
                if args.json
                else f"OpenFold3 validation report: {validation_report_path}"
            )
        else:
            approval = approve_openfold3_validation_report(
                report_path=args.report,
                reviewer=args.reviewer,
                decision=cast(
                    Literal["approve-default-switch", "reject-default-switch"],
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

    result: CommandResult
    if args.command == "project":
        result = (
            initialize_research_project(**_project_init_values(args))
            if args.project_command == "init"
            else project_status(args.project)
        )
    elif args.command == "target":
        result = (
            target_prepare(args.project, detach=args.detach)
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
            result = site_scan(args.project, method=args.method, detach=args.detach)
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
            result = strategy_freeze(args.project, config_path=args.config, confirm=args.confirm)
    elif args.command == "pilot":
        if args.pilot_command == "plan":
            result = pilot_plan(args.project, strategy_revision=args.strategy)
        elif args.pilot_command == "run":
            result = pilot_run(
                args.project,
                strategy_revision=args.strategy,
                confirm=args.confirm,
                detach=args.detach,
            )
        elif args.pilot_command == "review":
            result = pilot_review(args.project, run_id=args.run_id)
        else:
            result = pilot_promote(
                args.project,
                run_id=args.run_id,
                strategy_ids=tuple(
                    item.strip() for item in args.strategy.split(",") if item.strip()
                ),
                confirm=args.confirm,
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
            )
        )
    elif args.command == "select":
        result = (
            select_plan(args.project, run_id=args.run_id, top=args.top)
            if args.select_command == "plan"
            else select_run(
                args.project,
                run_id=args.run_id,
                top=args.top,
                confirm=args.confirm,
                detach=args.detach,
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
        summary = resolve_project_run(args.project, run_id=args.run_id, required=True)
        assert summary is not None
        report_root = resolve_target_viewer_argument(summary.path)
        server = create_target_viewer_server(
            report_root,
            port=args.port,
            stage02_overlay=build_stage02_viewer_overlay(summary.path),
            evidence=build_evidence_viewer_payload(summary.path),
        )
        internal = completed_steps(summary.path)
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
