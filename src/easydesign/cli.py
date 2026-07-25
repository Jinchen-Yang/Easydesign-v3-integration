"""EasyDesign Developer Preview 的薄命令行入口。"""

from __future__ import annotations

import argparse
import json
import sys
import traceback
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from pydantic import BaseModel

import easydesign
from easydesign.core import (
    ArtifactIntegrityError,
    ArtifactNotFoundError,
    ConfigurationError,
    EasyDesignError,
    SerializationError,
)
from easydesign.orchestration.application import (
    DiagnosticReport,
    PipelineExecution,
    RunPlan,
    diagnose_runtime,
    execute_pipeline,
    list_runs,
    migrate_run_configuration,
    show_run,
    validate_run_configuration,
)
from easydesign.orchestration.hotspots import approve_hotspots, export_hotspot_review
from easydesign.orchestration.profile import (
    default_runtime_profile_path,
    initialize_runtime_profile,
    load_runtime_profile,
)
from easydesign.orchestration.project import initialize_project
from easydesign.reporting import (
    HOST,
    create_target_viewer_server,
    resolve_target_viewer_argument,
)
from easydesign.stages.s02_hotspot_discovery import RegionMethod


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

    init_parser = commands.add_parser("init", help="从真实 target 创建最小用户项目")
    init_parser.add_argument("project_dir", type=Path)
    init_parser.add_argument("--target", type=Path, required=True)
    init_parser.add_argument("--project-id")
    init_parser.add_argument("--target-id")
    init_parser.add_argument("--stop-after", type=int, choices=(1, 2), default=1)
    init_parser.add_argument(
        "--stage02-method",
        choices=("sasa", "scannet", "both"),
        default="both",
        help="Stage 02 自动方法（默认 both）",
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
        help="将旧 YAML 显式迁移为 canonical 0.3",
    )
    config_migrate.add_argument("config", type=Path)
    config_migrate.add_argument("--output", type=Path, required=True)

    doctor_parser = commands.add_parser("doctor", help="检查本次运行所需环境")
    doctor_parser.add_argument("--config", type=Path)
    _add_profile(doctor_parser)
    doctor_parser.add_argument("--runs-root", type=Path)
    _add_json(doctor_parser)

    run_parser = commands.add_parser("run", help="执行 YAML 声明的已实现阶段")
    run_parser.add_argument("config", type=Path)
    _add_profile(run_parser)
    run_parser.add_argument("--runs-root", type=Path)
    run_parser.add_argument("--run-id")
    run_parser.add_argument("--dry-run", action="store_true")
    _add_json(run_parser)

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
        required=True,
    )
    hotspots_export.add_argument("--output", type=Path, required=True)
    hotspots_approve = hotspots_commands.add_parser(
        "approve",
        help="验证审批文件并发布 hotspots.yaml",
    )
    hotspots_approve.add_argument("run", type=Path)
    hotspots_approve.add_argument("--input", type=Path, required=True)

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

    viewer_parser = commands.add_parser("viewer", help="查看自包含结构报告")
    viewer_commands = viewer_parser.add_subparsers(dest="viewer_command", required=True)
    viewer_serve = viewer_commands.add_parser(
        "serve", help="仅在 127.0.0.1 提供已验证报告"
    )
    viewer_serve.add_argument("run", type=Path)
    viewer_serve.add_argument("--port", type=int, default=8000)
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
    print(f"运行成功：{execution.run_root}")
    print(f"Run manifest：{execution.run_manifest}")
    if execution.viewer_status is not None:
        print(f"Stage 01 Viewer：{execution.viewer_status}")


def _runs_root(explicit: Path | None, profile_path: Path | None) -> Path:
    if explicit is not None:
        return explicit.expanduser().resolve()
    selected = profile_path
    if selected is None and not default_runtime_profile_path().is_file():
        return (Path.cwd() / "runs").resolve()
    loaded = load_runtime_profile(selected)
    return (
        loaded.profile.runs_root.resolve()
        if loaded.profile.runs_root is not None
        else (Path.cwd() / "runs").resolve()
    )


def _dispatch(arguments: argparse.Namespace) -> int:
    if arguments.command == "init":
        initialized = initialize_project(
            project_root=arguments.project_dir,
            target=arguments.target,
            project_id=arguments.project_id,
            target_id=arguments.target_id,
            stop_after_stage=arguments.stop_after,
            stage02_method=arguments.stage02_method,
        )
        payload = {
            "project_root": str(initialized.project_root),
            "config": str(initialized.config_path),
            "target": str(initialized.target_path),
            "format": str(initialized.detected_format),
        }
        if arguments.json:
            print(_json_text(payload))
        else:
            print(f"项目已创建：{initialized.project_root}")
            print(f"下一步：easydesign config validate {initialized.config_path}")
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
        )
        if arguments.json:
            print(_json_text(execution))
        else:
            _print_execution(execution)
        return 0

    if arguments.command == "hotspots":
        if arguments.hotspots_command == "export":
            method = (
                RegionMethod.SASA_SURFACE_DIVERSITY
                if arguments.method == "sasa"
                else RegionMethod.SCANNET_EPITOPE_NO_MSA
            )
            output = export_hotspot_review(
                arguments.run,
                method=method,
                output=arguments.output,
            )
            print(f"Hotspot 审批模板已导出：{output}")
            print(
                "请填写 approved_by、每个区域的两类理由；structural-only "
                "还需确认 evidence limitations。"
            )
            return 0
        hotspots = approve_hotspots(
            arguments.run,
            input_path=arguments.input,
        )
        print(f"Stage 02 已批准：{hotspots}")
        return 0

    if arguments.command == "runs":
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
